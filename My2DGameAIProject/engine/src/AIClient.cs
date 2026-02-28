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
/// Async job workflow
/// ------------------
/// 1. Call <see cref="SubmitStoryJob"/> or <see cref="SubmitSpriteJob"/> to
///    enqueue work on the server and receive a <c>job_id</c> immediately.
/// 2. Call <see cref="PollJobUntilDone"/> with the returned <c>job_id</c> to
///    periodically poll the status endpoint until the job is "done" or "error".
///
/// Usage example:
///   string jobId = await aiClient.SubmitStoryJob("move north", "00023");
///   var result   = await aiClient.PollJobUntilDone(jobId, $"/story/status/{jobId}");
/// </summary>
public partial class AIClient : Node
{
    // -------------------------------------------------------------------------
    // Configuration – override via engine/configs/ai_client.cfg in production
    // -------------------------------------------------------------------------

    [Export] public string ServiceBaseUrl { get; set; } = "http://127.0.0.1:8000";
    [Export] public float TimeoutSeconds { get; set; } = 30f;

    /// <summary>Interval between polling attempts in seconds.</summary>
    [Export] public float PollIntervalSeconds { get; set; } = 1.5f;

    /// <summary>Maximum number of polling attempts before giving up.</summary>
    [Export] public int MaxPollAttempts { get; set; } = 60;

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
    // Async job queue API
    // -------------------------------------------------------------------------

    /// <summary>
    /// Submit a story generation job and return the <c>job_id</c>, or null on
    /// failure.
    /// </summary>
    public async Task<string> SubmitStoryJob(
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

        string response = await PostJsonAsync("/story/generate", payload);
        if (response == null) return null;

        var json = System.Text.Json.JsonDocument.Parse(response);
        return json.RootElement.TryGetProperty("job_id", out var jobIdProp)
            ? jobIdProp.GetString()
            : null;
    }

    /// <summary>
    /// Submit a sprite generation job and return the <c>job_id</c>, or null on
    /// failure.
    /// </summary>
    public async Task<string> SubmitSpriteJob(
        string playerInput,
        string worldStateId = "00000",
        int width = 64,
        int height = 64,
        float temperature = 0.72f,
        string sketchB64 = null)
    {
        var payload = new
        {
            player_input   = playerInput,
            world_state_id = worldStateId,
            width          = width,
            height         = height,
            temperature    = temperature,
            batch_mode     = true,
            sketch_b64     = sketchB64,
        };

        string response = await PostJsonAsync("/text2sprite/generate", payload);
        if (response == null) return null;

        var json = System.Text.Json.JsonDocument.Parse(response);
        return json.RootElement.TryGetProperty("job_id", out var jobIdProp)
            ? jobIdProp.GetString()
            : null;
    }

    /// <summary>
    /// Poll <paramref name="pollEndpoint"/> at regular intervals until the job
    /// status is <c>"done"</c> or <c>"error"</c>.
    ///
    /// Returns a <see cref="Godot.Collections.Dictionary"/> with the job
    /// result fields, or <c>null</c> on timeout / error.
    /// </summary>
    public async Task<Godot.Collections.Dictionary> PollJobUntilDone(
        string jobId,
        string pollEndpoint)
    {
        string url = ServiceBaseUrl.TrimEnd('/') + pollEndpoint;

        for (int attempt = 0; attempt < MaxPollAttempts; attempt++)
        {
            // Wait before polling (except on the very first attempt).
            if (attempt > 0)
                await ToSignalAsync(GetTree().CreateTimer(PollIntervalSeconds));

            string response = await GetAsync(pollEndpoint);
            if (response == null) continue;

            using var json = System.Text.Json.JsonDocument.Parse(response);
            var root = json.RootElement;

            string status = root.TryGetProperty("status", out var statusProp)
                ? statusProp.GetString()
                : "unknown";

            GD.Print($"[AIClient] Poll {jobId} attempt {attempt + 1}: {status}");

            if (status == "done")
            {
                // Convert the JSON result into a Godot Dictionary for easy
                // consumption by GDScript or other C# nodes.
                return ParseJobResult(root);
            }

            if (status == "error")
            {
                string errorMsg = root.TryGetProperty("error", out var errProp)
                    ? errProp.GetString()
                    : "unknown error";
                GD.PrintErr($"[AIClient] Job {jobId} failed: {errorMsg}");
                return null;
            }
        }

        GD.PrintErr($"[AIClient] Job {jobId} did not complete after {MaxPollAttempts} attempts.");
        return null;
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

    // -------------------------------------------------------------------------
    // Strongly-typed DTO helper (Step 5)
    // -------------------------------------------------------------------------

    /// <summary>
    /// Request a narrative beat and deserialise the response into a
    /// <see cref="GameStateDTO"/> using <c>System.Text.Json</c>.
    ///
    /// All errors – network timeouts, non-2xx HTTP status codes, and JSON
    /// deserialisation failures – are caught internally and result in a
    /// <c>null</c> return value (consistent with the rest of <see cref="AIClient"/>).
    /// No exceptions propagate to the caller.
    /// </summary>
    public async Task<GameStateDTO> RequestStoryDTO(
        string playerInput,
        string worldStateId = "00000",
        float temperature = 0.72f,
        int maxLen = 256)
    {
        string json = await RequestStory(playerInput, worldStateId, temperature, maxLen);
        return GameStateDTO.FromJson(json);
    }

    /// <summary>Issues a GET request to <paramref name="endpoint"/>.</summary>
    private async Task<string> GetAsync(string endpoint)
    {
        string url = ServiceBaseUrl.TrimEnd('/') + endpoint;

        try
        {
            GD.Print($"[AIClient] GET {url}");
            HttpResponseMessage response = await _httpClient.GetAsync(url);
            response.EnsureSuccessStatusCode();
            return await response.Content.ReadAsStringAsync();
        }
        catch (HttpRequestException ex)
        {
            GD.PrintErr($"[AIClient] HTTP error calling {url}: {ex.Message}");
            return null;
        }
        catch (TaskCanceledException)
        {
            GD.PrintErr($"[AIClient] GET {url} timed out.");
            return null;
        }
        catch (Exception ex)
        {
            GD.PrintErr($"[AIClient] Unexpected error calling {url}: {ex}");
            return null;
        }
    }

    /// <summary>
    /// Converts a flat JSON element into a Godot Dictionary for inter-node use.
    /// Only primitive string/bool/number values are included.
    /// </summary>
    private static Godot.Collections.Dictionary ParseJobResult(
        System.Text.Json.JsonElement root)
    {
        var dict = new Godot.Collections.Dictionary();
        foreach (var prop in root.EnumerateObject())
        {
            dict[prop.Name] = prop.Value.ValueKind switch
            {
                System.Text.Json.JsonValueKind.String  => (Variant)prop.Value.GetString(),
                System.Text.Json.JsonValueKind.Number  => (Variant)prop.Value.GetDouble(),
                System.Text.Json.JsonValueKind.True    => (Variant)true,
                System.Text.Json.JsonValueKind.False   => (Variant)false,
                System.Text.Json.JsonValueKind.Array   => (Variant)prop.Value.GetRawText(),
                _                                       => (Variant)prop.Value.GetRawText(),
            };
        }
        return dict;
    }

    /// <summary>
    /// Wraps a <see cref="SceneTreeTimer"/> timeout signal in a Task so we can
    /// use it with <c>await</c>.
    /// </summary>
    private static Task ToSignalAsync(SceneTreeTimer timer)
    {
        var tcs = new TaskCompletionSource<bool>();
        timer.Timeout += () => tcs.TrySetResult(true);
        return tcs.Task;
    }
}
