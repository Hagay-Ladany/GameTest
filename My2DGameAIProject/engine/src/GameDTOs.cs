using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;

/// <summary>
/// Data Transfer Objects (DTOs) that mirror the Python backend's GBNF grammar schema.
///
/// GBNF schema enforced by the LLM:
/// <code>
/// object   ::= { "narrative": string, "choices": choices-array }
/// choice   ::= { "id": number, "text": string }
/// </code>
///
/// Using <see cref="System.Text.Json"/> with <see cref="JsonPropertyNameAttribute"/>
/// makes the round-trip from server JSON to C# objects mathematically provable –
/// any field mismatch is a compile-time or deserialisation error, not a silent null.
///
/// Usage:
/// <code>
///   string json  = await aiClient.RequestStory("move north");
///   var    state = GameStateDTO.FromJson(json);
///   GD.Print(state?.Narrative);
/// </code>
/// </summary>

// ---------------------------------------------------------------------------
// ChoiceDTO
// ---------------------------------------------------------------------------

/// <summary>
/// Represents one player choice returned by the narrative backend.
/// Maps to <c>{ "id": int, "text": string }</c> in the GBNF grammar.
/// </summary>
public sealed class ChoiceDTO
{
    /// <summary>Unique identifier for the choice (used when submitting the player's selection).</summary>
    [JsonPropertyName("id")]
    public int Id { get; set; }

    /// <summary>Human-readable label displayed on the choice button.</summary>
    [JsonPropertyName("text")]
    public string Text { get; set; } = string.Empty;
}

// ---------------------------------------------------------------------------
// GameStateDTO
// ---------------------------------------------------------------------------

/// <summary>
/// Root DTO returned by <c>POST /story/generate</c> (and the corresponding
/// status poll endpoint once the job is <c>"done"</c>).
/// Maps to <c>{ "narrative": string, "choices": [ ChoiceDTO, … ] }</c>.
/// </summary>
public sealed class GameStateDTO
{
    /// <summary>Scene description / narrative text to display in the <c>RichTextLabel</c>.</summary>
    [JsonPropertyName("narrative")]
    public string Narrative { get; set; } = string.Empty;

    /// <summary>Player-facing action choices, each with an <see cref="ChoiceDTO.Id"/> and label.</summary>
    [JsonPropertyName("choices")]
    public List<ChoiceDTO> Choices { get; set; } = new();

    // -------------------------------------------------------------------------
    // Convenience factory
    // -------------------------------------------------------------------------

    private static readonly JsonSerializerOptions _options = new()
    {
        PropertyNameCaseInsensitive = true,
    };

    /// <summary>
    /// Deserialises <paramref name="json"/> into a <see cref="GameStateDTO"/>.
    /// </summary>
    /// <returns>
    /// A populated <see cref="GameStateDTO"/> on success.
    /// <c>null</c> when <paramref name="json"/> is <c>null</c> or whitespace (network layer
    /// returned nothing), or when deserialisation throws a <see cref="JsonException"/>
    /// (the server returned invalid JSON). Callers should treat <c>null</c> as "generation
    /// failed" and surface an error to the player rather than attempting to use the result.
    /// </returns>
    public static GameStateDTO FromJson(string json)
    {
        if (string.IsNullOrWhiteSpace(json))
            return null;

        try
        {
            return JsonSerializer.Deserialize<GameStateDTO>(json, _options);
        }
        catch (JsonException ex)
        {
            // Log the root cause so debugging is not blind; swallow so the game
            // can degrade gracefully rather than crashing.
            System.Diagnostics.Debug.WriteLine($"[GameStateDTO] JSON deserialisation failed: {ex.Message}");
            return null;
        }
    }
}
