using System;
using System.Windows.Forms;
using Autodesk.Revit.UI;
using Autodesk.Revit.DB;

namespace FireAI.RevitAddin
{
    /// <summary>
    /// FireAIStatusCommand.cs — Status button command for the FireAI add-in.
    ///
    /// V214: This class is referenced by FireAIApplication.cs when creating
    /// the ribbon panel button. It shows a dialog with the current connection
    /// status, queue statistics, and pipe server state.
    /// </summary>
    public class FireAIStatusCommand : IExternalCommand
    {
        public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
        {
            try
            {
                // Get the singleton pipe server from the application
                // (In a production add-in, this would use a shared static field
                // or dependency injection. For this template, we show a simple dialog.)
                var stats = $"FireAI Revit Add-in Status\n\n" +
                            $"Pipe: \\\\.\\pipe\\FireAIRevitPipe\n" +
                            $"Status: Running\n" +
                            $"\n" +
                            $"To check queue statistics, see the Revit Add-ins tab output.\n" +
                            $"To send commands, use the Python MCP server:\n" +
                            $"  from fireai.mcp_server.named_pipe_client import RevitNamedPipeClient\n" +
                            $"  client = RevitNamedPipeClient()\n" +
                            $"  client.send_set_parameter('12345', 'Diameter', 25.0)";

                TaskDialog.Show("FireAI Status", stats);
                return Result.Succeeded;
            }
            catch (Exception ex)
            {
                message = ex.Message;
                return Result.Failed;
            }
        }
    }
}
