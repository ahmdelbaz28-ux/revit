using System;
using System.Threading;
using Autodesk.AutoCAD.Runtime;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Windows;

[assembly: ExtensionApplication(typeof(BazSparkAutoCADBridge.Application))]

namespace BazSparkAutoCADBridge
{
    /// <summary>
    /// Entry point for the BAZspark AutoCAD Add-in.
    /// Implements IExtensionApplication to handle AutoCAD startup and shutdown.
    /// Launches the Named Pipe server to listen for local Python agent commands.
    /// </summary>
    public class Application : IExtensionApplication
    {
        private LocalAgentServer? _pipeServer;
        private Thread? _pipeThread;
        private static PaletteSet? _paletteSet;

        public void Initialize()
        {
            try
            {
                // 1. Initialize and start the Named Pipe server on a background thread
                _pipeServer = new LocalAgentServer();
                _pipeThread = new Thread(_pipeServer.Start)
                {
                    IsBackground = true,
                    Name = "BazSparkAutoCADPipeServer"
                };
                _pipeThread.Start();

                // 2. Safely output startup status message to AutoCAD command line
                WriteToCommandLine("\n✅ BAZspark AutoCAD Bridge started.\n" +
                                    "Listening on named pipe: \\\\.\\pipe\\bazspark_autocad\n" +
                                    "Type command BAZSPARKPANEL to open the embedded Web Dashboard.\n");
            }
            catch (System.Exception ex)
            {
                WriteToCommandLine($"\n❌ BAZspark Bridge Startup failed: {ex.Message}\n");
            }
        }

        public void Terminate()
        {
            try
            {
                _pipeServer?.Stop();
                _pipeThread?.Join(TimeSpan.FromSeconds(2));
            }
            catch
            {
                // Best effort cleanup on shutdown
            }
        }

        /// <summary>
        /// Command to open the BAZspark WebView2 Dockable Palette.
        /// </summary>
        [CommandMethod("BAZSPARKPANEL")]
        public static void ShowBazSparkPanel()
        {
            try
            {
                if (_paletteSet == null)
                {
                    _paletteSet = new PaletteSet(
                        "BAZspark Dashboard",
                        new Guid("9E067D25-0E56-4DAB-805F-6A81427EB2E6"));

                    var control = new WebPanelControl();
                    _paletteSet.AddVisual("BAZspark Web UI", control);

                    _paletteSet.Size = new System.Drawing.Size(400, 600);
                    _paletteSet.MinimumSize = new System.Drawing.Size(200, 300);
                }

                _paletteSet.Visible = true;
            }
            catch (System.Exception ex)
            {
                WriteToCommandLine($"\n❌ Failed to open BAZspark Panel: {ex.Message}\n");
            }
        }

        /// <summary>
        /// Helper to write messages to the AutoCAD Command Line.
        /// </summary>
        public static void WriteToCommandLine(string message)
        {
            try
            {
                var doc = Autodesk.AutoCAD.ApplicationServices.Application.DocumentManager.MdiActiveDocument;
                if (doc != null)
                {
                    doc.Editor.WriteMessage(message);
                }
            }
            catch
            {
                // Fallback if MdiActiveDocument or Editor is not yet initialized
            }
        }
    }
}
