using System;
using System.IO;
using System.IO.Pipes;
using System.Text;
using System.Threading;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using Autodesk.AutoCAD.ApplicationServices;

namespace BazSparkAutoCADBridge
{
    public class LocalAgentServer
    {
        private const string PIPE_NAME = "bazspark_autocad";
        private volatile bool _running = false;

        public void Start()
        {
            _running = true;
            while (_running)
            {
                try
                {
                    // Starts the secure named pipe server listener
                    using var pipe = CreateSecurePipe();

                    pipe.WaitForConnection(); // Blocks until local Python agent connects
                    HandleClient(pipe);
                }
                catch (Exception ex) when (_running)
                {
                    System.Diagnostics.Debug.WriteLine($"[BazSpark AutoCAD] Pipe error: {ex.Message}");
                    Thread.Sleep(500);
                }
            }
        }

        private NamedPipeServerStream CreateSecurePipe()
        {
            var pipeSecurity = new PipeSecurity();
            var currentIdentity = System.Security.Principal.WindowsIdentity.GetCurrent();

            // Allow only current user
            pipeSecurity.AddAccessRule(new PipeAccessRule(
                currentIdentity.User,
                PipeAccessRights.FullControl,
                System.Security.AccessControl.AccessControlType.Allow));

            // Allow system/administrators
            pipeSecurity.AddAccessRule(new PipeAccessRule(
                new System.Security.Principal.SecurityIdentifier(System.Security.Principal.WellKnownSidType.BuiltinAdministratorsSid, null),
                PipeAccessRights.FullControl,
                System.Security.AccessControl.AccessControlType.Allow));

            return new NamedPipeServerStream(
                PIPE_NAME,
                PipeDirection.InOut,
                NamedPipeServerStream.MaxAllowedServerInstances,
                PipeTransmissionMode.Message,
                PipeOptions.None,
                1024,
                1024,
                pipeSecurity);
        }

        public void Stop() => _running = false;

        private void HandleClient(NamedPipeServerStream pipe)
        {
            using var reader = new StreamReader(pipe, Encoding.UTF8, true, 1024, true);
            using var writer = new StreamWriter(pipe, Encoding.UTF8, 1024, true) { AutoFlush = true };

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
                    string action = payload["action"]?.ToString() ?? "";
                    var parameters = payload["params"] as JObject ?? new JObject();

                    // AutoCAD thread safety: We must lock the MdiActiveDocument
                    // to safely manipulate document objects from our background Named Pipe thread.
                    var doc = Autodesk.AutoCAD.ApplicationServices.Application.DocumentManager.MdiActiveDocument;
                    if (doc == null)
                    {
                        throw new InvalidOperationException("No active AutoCAD document.");
                    }

                    object result;
                    using (doc.LockDocument())
                    {
                        result = AutoCADCommandHandler.DispatchCommand(doc, action, parameters);
                    }

                    response = JsonConvert.SerializeObject(new { success = true, data = result });
                }
                catch (Exception ex)
                {
                    response = JsonConvert.SerializeObject(new { success = false, error = ex.Message });
                }

                try
                {
                    writer.WriteLine(response);
                }
                catch
                {
                    break; // Connection lost
                }
            }
        }
    }
}
