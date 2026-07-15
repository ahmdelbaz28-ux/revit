// BazSparkRevitBridge/LocalAgentServer.cs
// Named Pipe server that listens for JSON commands from the BAZspark Python Local Agent.
// Runs on a background thread; enqueues commands to the ExternalEventHandler
// and waits synchronously for the result (with a timeout).

using System;
using System.IO;
using System.IO.Pipes;
using System.Text;
using System.Threading;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace BazSparkRevitBridge
{
    public class LocalAgentServer
    {
        private const string PIPE_NAME    = "bazspark_revit";
        private const int    TIMEOUT_MS   = 30_000; // 30 seconds per command
        private const int    MAX_MSG_BYTES = 10 * 1024 * 1024; // 10 MB

        private readonly BazSparkExternalEventHandler _handler;
        private volatile bool _running = false;

        public LocalAgentServer(BazSparkExternalEventHandler handler)
        {
            _handler = handler;
        }

        public void Start()
        {
            _running = true;
            while (_running)
            {
                try
                {
                    // Each iteration handles one client connection (Python Agent)
                    using var pipe = new NamedPipeServerStream(
                        PIPE_NAME,
                        PipeDirection.InOut,
                        NamedPipeServerStream.MaxAllowedServerInstances,
                        PipeTransmissionMode.Message,
                        PipeOptions.None);

                    pipe.WaitForConnection(); // Blocks until Python Agent connects
                    HandleClient(pipe);
                }
                catch (Exception ex) when (_running)
                {
                    // Log and restart listener on transient errors
                    System.Diagnostics.Debug.WriteLine($"[BazSpark] Pipe error: {ex.Message}");
                    Thread.Sleep(500);
                }
            }
        }

        public void Stop() => _running = false;

        private void HandleClient(NamedPipeServerStream pipe)
        {
            // Read all incoming bytes (one JSON message per connection)
            using var reader = new StreamReader(pipe, Encoding.UTF8, leaveOpen: true);
            using var writer = new StreamWriter(pipe, Encoding.UTF8, leaveOpen: true)
                { AutoFlush = true };

            while (pipe.IsConnected)
            {
                string? line;
                try { line = reader.ReadLine(); }
                catch { break; }

                if (string.IsNullOrWhiteSpace(line)) continue;

                string response;
                try
                {
                    var payload = JObject.Parse(line);
                    var cmd = new BazSparkCommand
                    {
                        CommandId = payload["command_id"]?.ToString() ?? Guid.NewGuid().ToString(),
                        Action    = payload["action"]?.ToString() ?? "",
                        Params    = payload["params"] as JObject ?? new JObject()
                    };

                    // Enqueue and trigger Revit's ExternalEvent
                    _handler.Enqueue(cmd);

                    // Wait for the ExternalEventHandler to process it (on Revit's main thread)
                    bool finished = cmd.Done.Wait(TIMEOUT_MS);
                    response = finished
                        ? cmd.ResultJson ?? "{\"success\":false,\"error\":\"No result\"}"
                        : JsonConvert.SerializeObject(new { success = false, error = "Timeout: Revit did not process command in 30s" });
                }
                catch (Exception ex)
                {
                    response = JsonConvert.SerializeObject(new { success = false, error = ex.Message });
                }

                writer.WriteLine(response);
            }
        }
    }
}
