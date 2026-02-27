using Godot;
using System;
using System.Text;
using System.Threading.Tasks;
using System.Net.Http;
using System.Net.Http.Headers;

/// <summary>
/// AIClient – Godot 4.x C# script that sends asynchronous HTTP requests to
/// the My2DGameAI Python FastAPI microservices without blocking the main
/// game thread.
///
/// Attach this script to an AutoLoad singleton node (e.g. "AIClient") so that
/// any scene in the project can call it via GetNode&lt;AIClient&gt;("/root/AIClient").
///
/// Usage example:
///   var response = await AIClient.RequestSprite("a knight in golden armour", "00023");
///   GD.Print(response);
/// </summary>
public partial class AIClient : Node
{
    // -------------------------------------------------------------------------
    // Configuration – override via engine/configs/ai_client.cfg in production
    // -------------------------------------------------------------------------

    [Export] public string ServiceBaseUrl { get; set; } = "http://127.0.0.1:8000";
    [Export] public float TimeoutSeconds { get; set; } = 30f;

    // Shared HttpClient – reuse across requests to avoid socket exhaustion.
    // Initialised with sensible defaults; _Ready() may override timeout.
    // This class is designed to be used as a Godot AutoLoad singleton (one
    // instance for the lifetime of the game), so a shared static client is safe.
    private static readonly HttpClient _httpClient = new()
    {
        Timeout = TimeSpan.FromSeconds(30),
        DefaultRequestHeaders = { Accept = { new MediaTypeWithQualityHeaderValue("application/json") } },
    };

    // -------------------------------------------------------------------------
    // Godot lifecycle
    // -------------------------------------------------------------------------

    public override void _Ready()
    {
        // Allow the exported property to override the default timeout at runtime.
        _httpClient.Timeout = TimeSpan.FromSeconds(TimeoutSeconds);
        GD.Print($"[AIClient] Initialised. Service URL: {ServiceBaseUrl}");
    }

    // -------------------------------------------------------------------------
    // Public API – called from GDScript or other C# nodes
    // -------------------------------------------------------------------------

    /// <summary>
    /// Request a sprite from the text-to-sprite microservice.
    /// Returns the raw JSON response string, or null on failure.
    /// </summary>
    public async Task<string> RequestSprite(
        string playerInput,
        string worldStateId = "00000",
        int width = 64,
        int height = 64,
        float temperature = 0.72f)
    {
        var payload = new
        {
            player_input  = playerInput,
            world_state_id = worldStateId,
            width         = width,
            height        = height,
            temperature   = temperature,
            batch_mode    = true,
        };
        return await PostJsonAsync("/text2sprite/generate", payload);
    }

    /// <summary>
    /// Request a narrative beat from the story-engine microservice.
    /// Returns the raw JSON response string, or null on failure.
    /// </summary>
    public async Task<string> RequestStory(
        string playerInput,
        string worldStateId = "00000",
        float temperature = 0.72f,
        int maxLen = 256)
    {
        var payload = new
        {
            player_input   = playerInput,
            world_state_id = worldStateId,
            temperature    = temperature,
            max_len        = maxLen,
            batch_mode     = true,
        };
        return await PostJsonAsync("/story/generate", payload);
    }

    // -------------------------------------------------------------------------
    // Internal helpers
    // -------------------------------------------------------------------------

    /// <summary>
    /// Serialises <paramref name="payload"/> to JSON and POSTs it to
    /// <paramref name="endpoint"/> on the AI service.  All network I/O runs on
    /// a background thread via async/await so the Godot main thread is never
    /// blocked.
    /// </summary>
    private async Task<string> PostJsonAsync(string endpoint, object payload)
    {
        string url = ServiceBaseUrl.TrimEnd('/') + endpoint;

        try
        {
            string json = System.Text.Json.JsonSerializer.Serialize(payload);
            using var content = new StringContent(json, Encoding.UTF8, "application/json");

            GD.Print($"[AIClient] POST {url}");
            HttpResponseMessage response = await _httpClient.PostAsync(url, content);
            response.EnsureSuccessStatusCode();

            string body = await response.Content.ReadAsStringAsync();
            GD.Print($"[AIClient] Response ({(int)response.StatusCode}): {body}");
            return body;
        }
        catch (HttpRequestException ex)
        {
            GD.PrintErr($"[AIClient] HTTP error calling {url}: {ex.Message}");
            return null;
        }
        catch (TaskCanceledException)
        {
            GD.PrintErr($"[AIClient] Request to {url} timed out after {TimeoutSeconds}s.");
            return null;
        }
        catch (Exception ex)
        {
            GD.PrintErr($"[AIClient] Unexpected error calling {url}: {ex}");
            return null;
        }
    }
}
