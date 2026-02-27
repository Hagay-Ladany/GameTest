using Godot;
using System;
using System.Threading.Tasks;

/// <summary>
/// GameStateMachine – class-based Finite State Machine (FSM) that manages the
/// high-level phases of an AI-driven game turn.
///
/// Unlike a Node-based FSM, this lightweight class holds no scene-tree
/// references of its own, which keeps the logic decoupled from the scene
/// hierarchy and easy to unit-test.
///
/// States
/// ------
/// <list type="bullet">
///   <item><see cref="GameState.Idle"/>        – awaits player input; UI is interactive.</item>
///   <item><see cref="GameState.Request"/>      – dispatches LLM call; UI is locked.</item>
///   <item><see cref="GameState.Asset"/>        – polls the SDXL queue until sprite is ready.</item>
///   <item><see cref="GameState.Presentation"/> – animates narrative text and buttons.</item>
/// </list>
///
/// Usage:
/// <code>
///   var fsm = new GameStateMachine(aiClient, spriteController);
///   fsm.OnStateChanged += newState => GD.Print("State: " + newState);
///   await fsm.SubmitPlayerChoice("move north");
/// </code>
/// </summary>
public class GameStateMachine
{
    // -------------------------------------------------------------------------
    // State enumeration
    // -------------------------------------------------------------------------

    public enum GameState
    {
        Idle,
        Request,
        Asset,
        Presentation,
    }

    // -------------------------------------------------------------------------
    // Events
    // -------------------------------------------------------------------------

    /// <summary>Fired whenever the FSM transitions to a new state.</summary>
    public event Action<GameState> OnStateChanged;

    /// <summary>Fired when a narrative + choices payload is ready to display.</summary>
    public event Action<string, Godot.Collections.Array> OnNarrativeReady;

    /// <summary>Fired when an error occurs during the AI pipeline.</summary>
    public event Action<string> OnError;

    // -------------------------------------------------------------------------
    // Dependencies (injected via constructor)
    // -------------------------------------------------------------------------

    private readonly AIClient _aiClient;
    private readonly SpriteController _spriteController;

    // -------------------------------------------------------------------------
    // State
    // -------------------------------------------------------------------------

    public GameState CurrentState { get; private set; } = GameState.Idle;

    // -------------------------------------------------------------------------
    // Construction
    // -------------------------------------------------------------------------

    public GameStateMachine(AIClient aiClient, SpriteController spriteController)
    {
        _aiClient = aiClient;
        _spriteController = spriteController;
    }

    // -------------------------------------------------------------------------
    // Public API
    // -------------------------------------------------------------------------

    /// <summary>
    /// Drives a complete AI-assisted turn from player input through sprite
    /// generation to UI presentation.
    /// </summary>
    /// <param name="playerInput">The player's chosen action text.</param>
    /// <param name="worldStateId">Opaque world-state identifier sent to the backend.</param>
    /// <param name="sketchB64">
    ///   Optional base64-encoded PNG sketch for ControlNet conditioning.
    /// </param>
    public async Task SubmitPlayerChoice(
        string playerInput,
        string worldStateId = "00000",
        string sketchB64 = null)
    {
        if (CurrentState != GameState.Idle)
        {
            GD.PrintErr("[FSM] SubmitPlayerChoice called while not Idle – ignoring.");
            return;
        }

        // ── Phase 1: Request ─────────────────────────────────────────────────
        TransitionTo(GameState.Request);

        string storyJobId = await _aiClient.SubmitStoryJob(playerInput, worldStateId);
        if (storyJobId == null)
        {
            HandleError("Failed to submit story job.");
            return;
        }

        // Poll until narrative is ready.
        var narrativeResult = await _aiClient.PollJobUntilDone(
            storyJobId,
            pollEndpoint: $"/story/status/{storyJobId}");

        if (narrativeResult == null)
        {
            HandleError("Story job timed out or failed.");
            return;
        }

        // ── Phase 2: Asset ───────────────────────────────────────────────────
        TransitionTo(GameState.Asset);

        string spriteJobId = await _aiClient.SubmitSpriteJob(playerInput, worldStateId, sketchB64: sketchB64);
        if (spriteJobId == null)
        {
            HandleError("Failed to submit sprite job.");
            return;
        }

        // Poll until sprite is ready.
        var spriteResult = await _aiClient.PollJobUntilDone(
            spriteJobId,
            pollEndpoint: $"/text2sprite/status/{spriteJobId}");

        if (spriteResult != null)
        {
            _spriteController?.ApplySpriteFromPath(
                spriteResult.TryGetValue("sprite_path", out var path) ? path?.AsString() : null);
        }

        // ── Phase 3: Presentation ────────────────────────────────────────────
        TransitionTo(GameState.Presentation);

        string narrative = narrativeResult.TryGetValue("narrative", out var narr)
            ? narr?.AsString() ?? string.Empty
            : string.Empty;

        var choices = narrativeResult.TryGetValue("choices", out var ch)
            ? ch?.AsGodotArray() ?? new Godot.Collections.Array()
            : new Godot.Collections.Array();

        OnNarrativeReady?.Invoke(narrative, choices);

        // Return to Idle after presentation is triggered.
        TransitionTo(GameState.Idle);
    }

    // -------------------------------------------------------------------------
    // Internal helpers
    // -------------------------------------------------------------------------

    private void TransitionTo(GameState newState)
    {
        GD.Print($"[FSM] {CurrentState} → {newState}");
        CurrentState = newState;
        OnStateChanged?.Invoke(newState);
    }

    private void HandleError(string message)
    {
        GD.PrintErr($"[FSM] Error: {message}");
        OnError?.Invoke(message);
        TransitionTo(GameState.Idle);
    }
}
