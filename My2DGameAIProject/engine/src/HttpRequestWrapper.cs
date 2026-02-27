using Godot;
using System;
using System.Threading.Tasks;

/// <summary>
/// HttpRequestWrapper – wraps a Godot <see cref="HttpRequest"/> node in a C#
/// <see cref="Task{T}"/> so callers can use <c>await</c> instead of wiring
/// signal callbacks.
///
/// Timeout protection is achieved with <see cref="Task.WhenAny"/> and a
/// <see cref="SceneTreeTimer"/> so the main thread is never soft-locked if the
/// server hangs.
///
/// Usage:
/// <code>
///   var wrapper = new HttpRequestWrapper(this);
///   AddChild(wrapper.Node);
///   string body = await wrapper.PostJsonAsync("http://127.0.0.1:8000/story/generate", jsonPayload);
/// </code>
/// </summary>
public class HttpRequestWrapper
{
    // -------------------------------------------------------------------------
    // Public surface
    // -------------------------------------------------------------------------

    /// <summary>The underlying Godot HttpRequest node added to the scene.</summary>
    public HttpRequest Node { get; }

    private readonly Node _owner;

    public HttpRequestWrapper(Node owner)
    {
        _owner = owner;
        Node = new HttpRequest();
    }

    // -------------------------------------------------------------------------
    // GET
    // -------------------------------------------------------------------------

    /// <summary>
    /// Issues a GET request to <paramref name="url"/> and returns the response
    /// body as a string.  Returns <c>null</c> on failure or timeout.
    /// </summary>
    public Task<string> GetAsync(string url, float timeoutSeconds = 30f)
    {
        return SendAsync(url, HttpClient.Method.Get, null, timeoutSeconds);
    }

    // -------------------------------------------------------------------------
    // POST
    // -------------------------------------------------------------------------

    /// <summary>
    /// Issues a POST request with a JSON body and returns the response body.
    /// Returns <c>null</c> on failure or timeout.
    /// </summary>
    public Task<string> PostJsonAsync(string url, string jsonBody, float timeoutSeconds = 30f)
    {
        return SendAsync(url, HttpClient.Method.Post, jsonBody, timeoutSeconds);
    }

    // -------------------------------------------------------------------------
    // Core implementation
    // -------------------------------------------------------------------------

    private async Task<string> SendAsync(
        string url,
        HttpClient.Method method,
        string body,
        float timeoutSeconds)
    {
        var tcs = new TaskCompletionSource<string>();

        // Wire the one-shot signal handler.
        void OnCompleted(long result, long responseCode, string[] headers, byte[] bodyBytes)
        {
            if (result != (long)HttpRequest.Result.Success || responseCode < 200 || responseCode >= 300)
            {
                GD.PrintErr($"[HttpRequestWrapper] HTTP error – result={result}, code={responseCode}");
                tcs.TrySetResult(null);
            }
            else
            {
                tcs.TrySetResult(bodyBytes.GetStringFromUtf8());
            }
        }

        Node.RequestCompleted += OnCompleted;

        try
        {
            string[] requestHeaders = method == HttpClient.Method.Post
                ? new[] { "Content-Type: application/json" }
                : Array.Empty<string>();

            Error err = Node.Request(url, requestHeaders, method, body ?? string.Empty);
            if (err != Error.Ok)
            {
                GD.PrintErr($"[HttpRequestWrapper] Failed to start request: {err}");
                return null;
            }

            // Timeout guard – use SceneTreeTimer so it is frame-rate independent.
            var timerTask = ToSignalTask(_owner.GetTree().CreateTimer(timeoutSeconds));
            Task completed = await Task.WhenAny(tcs.Task, timerTask);

            if (completed != tcs.Task)
            {
                GD.PrintErr($"[HttpRequestWrapper] Request to {url} timed out after {timeoutSeconds}s.");
                Node.CancelRequest();
                return null;
            }

            return tcs.Task.Result;
        }
        finally
        {
            Node.RequestCompleted -= OnCompleted;
        }
    }

    // -------------------------------------------------------------------------
    // Helper – wrap SceneTreeTimer timeout signal in a Task
    // -------------------------------------------------------------------------

    private static Task ToSignalTask(SceneTreeTimer timer)
    {
        var tcs = new TaskCompletionSource<bool>();
        timer.Timeout += () => tcs.TrySetResult(true);
        return tcs.Task;
    }
}
