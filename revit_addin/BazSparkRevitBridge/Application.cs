// BazSparkRevitBridge/Application.cs
// Entry point for the BAZspark Revit Add-in.
// Registers an ExternalEvent handler and starts a Named Pipe server
// that receives commands from the BAZspark Local Agent (Python)
// and executes them safely on Revit's main thread via IExternalEventHandler.

using System;
using System.Threading;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;

namespace BazSparkRevitBridge
{
    /// <summary>
    /// IExternalApplication — Revit calls this at startup/shutdown.
    /// Responsible for registering the ExternalEvent and launching the pipe server.
    /// </summary>
    [Transaction(TransactionMode.Manual)]
    public class Application : IExternalApplication
    {
        internal static ExternalEvent? BazSparkEvent { get; private set; }
        internal static BazSparkExternalEventHandler? EventHandler { get; private set; }
        private LocalAgentServer? _pipeServer;
        private Thread? _pipeThread;

        public Result OnStartup(UIControlledApplication application)
        {
            try
            {
                // 1. Create the ExternalEvent handler (executes on Revit main thread)
                EventHandler = new BazSparkExternalEventHandler();
                BazSparkEvent = ExternalEvent.Create(EventHandler);

                // 2. Start Named Pipe server on a background thread
                _pipeServer = new LocalAgentServer(EventHandler);
                _pipeThread = new Thread(_pipeServer.Start)
                {
                    IsBackground = true,
                    Name = "BazSparkPipeServer"
                };
                _pipeThread.Start();

                TaskDialog.Show(
                    "BAZspark Bridge",
                    "✅ BAZspark Revit Bridge started.\n" +
                    "Listening on named pipe: \\\\.\\pipe\\bazspark_revit\n\n" +
                    "The Local Agent can now send Revit commands safely via this bridge."
                );

                return Result.Succeeded;
            }
            catch (Exception ex)
            {
                TaskDialog.Show("BAZspark Bridge Error", $"Startup failed: {ex.Message}");
                return Result.Failed;
            }
        }

        public Result OnShutdown(UIControlledApplication application)
        {
            try
            {
                _pipeServer?.Stop();
                _pipeThread?.Join(TimeSpan.FromSeconds(2));
                BazSparkEvent?.Dispose();
            }
            catch { /* Best effort shutdown */ }

            return Result.Succeeded;
        }
    }
}
