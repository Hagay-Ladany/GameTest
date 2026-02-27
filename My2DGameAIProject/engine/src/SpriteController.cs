using Godot;
using System;

/// <summary>
/// SpriteController – manages runtime texture application, physics shape
/// synchronisation and the reactive narrative UI (typewriter effect +
/// dynamically instantiated choice buttons).
///
/// Attach this script to the scene node that owns the <see cref="Sprite2D"/>,
/// <see cref="CollisionShape2D"/>, <see cref="RichTextLabel"/> and
/// <see cref="VBoxContainer"/> for player choices.
///
/// Physics note
/// ------------
/// Godot 4 deprecates <c>RectangleShape2D.Extents</c> in favour of
/// <c>RectangleShape2D.Size</c>.  This class uses the new API exclusively.
/// </summary>
public partial class SpriteController : Node
{
    // -------------------------------------------------------------------------
    // Exported scene references – assign in the Godot editor
    // -------------------------------------------------------------------------

    [Export] public NodePath SpritePath { get; set; }
    [Export] public NodePath CollisionShapePath { get; set; }
    [Export] public NodePath NarrativeLabelPath { get; set; }
    [Export] public NodePath ChoicesContainerPath { get; set; }

    /// <summary>Duration of the typewriter animation in seconds.</summary>
    [Export] public float TypewriterDuration { get; set; } = 2.5f;

    // -------------------------------------------------------------------------
    // Cached node references
    // -------------------------------------------------------------------------

    private Sprite2D _sprite;
    private CollisionShape2D _collisionShape;
    private RichTextLabel _narrativeLabel;
    private VBoxContainer _choicesContainer;

    // -------------------------------------------------------------------------
    // Godot lifecycle
    // -------------------------------------------------------------------------

    public override void _Ready()
    {
        if (SpritePath != null) _sprite = GetNodeOrNull<Sprite2D>(SpritePath);
        if (CollisionShapePath != null) _collisionShape = GetNodeOrNull<CollisionShape2D>(CollisionShapePath);
        if (NarrativeLabelPath != null) _narrativeLabel = GetNodeOrNull<RichTextLabel>(NarrativeLabelPath);
        if (ChoicesContainerPath != null) _choicesContainer = GetNodeOrNull<VBoxContainer>(ChoicesContainerPath);
    }

    // -------------------------------------------------------------------------
    // Runtime texture instantiation
    // -------------------------------------------------------------------------

    /// <summary>
    /// Decode <paramref name="pngBytes"/> into an <see cref="ImageTexture"/>
    /// using the Godot 4 factory method and apply it to the <see cref="Sprite2D"/>.
    /// Also updates the collision shape to match the new texture size.
    /// </summary>
    public void ApplySpriteFromBytes(byte[] pngBytes)
    {
        if (_sprite == null)
        {
            GD.PrintErr("[SpriteController] Sprite2D node not assigned.");
            return;
        }

        var image = new Image();
        Error err = image.LoadPngFromBuffer(pngBytes);
        if (err != Error.Ok)
        {
            GD.PrintErr($"[SpriteController] Failed to decode PNG: {err}");
            return;
        }

        ImageTexture texture = ImageTexture.CreateFromImage(image);
        _sprite.Texture = texture;

        SyncCollisionShape(new Vector2(image.GetWidth(), image.GetHeight()));
    }

    /// <summary>
    /// Load a sprite from a file path (for locally cached assets).
    /// Silently no-ops if <paramref name="path"/> is null or empty.
    /// </summary>
    public void ApplySpriteFromPath(string path)
    {
        if (string.IsNullOrEmpty(path)) return;

        // ResourceLoader.Load can handle local paths returned by the backend.
        var texture = ResourceLoader.Load<Texture2D>(path);
        if (texture == null)
        {
            GD.PrintErr($"[SpriteController] Could not load texture from: {path}");
            return;
        }

        if (_sprite != null)
        {
            _sprite.Texture = texture;
            SyncCollisionShape(texture.GetSize());
        }
    }

    // -------------------------------------------------------------------------
    // Physics synchronisation
    // -------------------------------------------------------------------------

    /// <summary>
    /// Updates the <see cref="RectangleShape2D"/> attached to the
    /// <see cref="CollisionShape2D"/> to match <paramref name="textureSize"/>.
    ///
    /// Uses <c>RectangleShape2D.Size</c> (Godot 4 API); the legacy
    /// <c>Extents</c> property is deprecated.
    /// </summary>
    private void SyncCollisionShape(Vector2 textureSize)
    {
        if (_collisionShape?.Shape is RectangleShape2D rect)
        {
            rect.Size = textureSize;
        }
    }

    // -------------------------------------------------------------------------
    // Reactive narrative UI – typewriter effect
    // -------------------------------------------------------------------------

    /// <summary>
    /// Animates <paramref name="text"/> into the <see cref="RichTextLabel"/>
    /// using a <see cref="Tween"/> that interpolates <c>visible_ratio</c>.
    ///
    /// This is frame-rate independent and more efficient than accumulating
    /// characters manually in <c>_Process</c>.
    /// </summary>
    public void PlayTypewriterEffect(string text)
    {
        if (_narrativeLabel == null)
        {
            GD.PrintErr("[SpriteController] RichTextLabel node not assigned.");
            return;
        }

        _narrativeLabel.Text = text;
        _narrativeLabel.VisibleRatio = 0f;

        Tween tween = CreateTween();
        tween.TweenProperty(
            _narrativeLabel,
            "visible_ratio",
            /* to */ 1.0f,
            TypewriterDuration
        );
    }

    // -------------------------------------------------------------------------
    // Reactive narrative UI – dynamic choice buttons
    // -------------------------------------------------------------------------

    /// <summary>
    /// Clears any existing buttons from <see cref="_choicesContainer"/> and
    /// instantiates a new <see cref="Button"/> for each choice in
    /// <paramref name="choices"/>.
    ///
    /// Each button's <c>Pressed</c> signal is bound via a C# lambda that
    /// calls <paramref name="onChoiceSelected"/> with the choice's id.
    /// </summary>
    /// <param name="choices">
    ///   Array of <see cref="Godot.Collections.Dictionary"/> objects, each with
    ///   keys <c>"id"</c> (int) and <c>"text"</c> (string).
    /// </param>
    /// <param name="onChoiceSelected">
    ///   Callback invoked with the selected choice id when the player clicks
    ///   a button.
    /// </param>
    public void PopulateChoiceButtons(
        Godot.Collections.Array choices,
        Action<int> onChoiceSelected)
    {
        if (_choicesContainer == null)
        {
            GD.PrintErr("[SpriteController] VBoxContainer node not assigned.");
            return;
        }

        // Remove previously instantiated buttons.
        foreach (Node child in _choicesContainer.GetChildren())
        {
            child.QueueFree();
        }

        foreach (var item in choices)
        {
            if (item.Obj is not Godot.Collections.Dictionary choice) continue;

            int id = choice.TryGetValue("id", out var idVar) ? idVar.AsInt32() : -1;
            string text = choice.TryGetValue("text", out var textVar) ? textVar.AsString() : "…";

            var button = new Button { Text = text };

            // Capture id in the lambda so each button dispatches its own id.
            int capturedId = id;
            button.Pressed += () => onChoiceSelected?.Invoke(capturedId);

            _choicesContainer.AddChild(button);
        }
    }
}
