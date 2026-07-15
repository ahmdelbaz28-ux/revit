// BazSparkRevitBridge/BazSparkExternalEventHandler.cs
// The core IExternalEventHandler that executes Revit API calls on the main thread.
// The Named Pipe server queues BazSparkCommand objects here;
// when Revit raises the ExternalEvent, this handler dequeues and executes them.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Architecture;
using Autodesk.Revit.UI;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace BazSparkRevitBridge
{
    /// <summary>
    /// Represents a command sent from the BAZspark Python Local Agent.
    /// </summary>
    public class BazSparkCommand
    {
        [JsonProperty("command_id")]  public string CommandId { get; set; } = Guid.NewGuid().ToString();
        [JsonProperty("action")]      public string Action    { get; set; } = "";
        [JsonProperty("params")]      public JObject Params   { get; set; } = new JObject();
        // The result will be written back here so the pipe server can respond
        public string? ResultJson { get; set; }
        public readonly System.Threading.ManualResetEventSlim Done = new(false);
    }

    /// <summary>
    /// Thread-safe queue + IExternalEventHandler.
    /// Commands are enqueued by the Named Pipe thread; Execute() runs on Revit's main thread.
    /// </summary>
    public class BazSparkExternalEventHandler : IExternalEventHandler
    {
        private readonly ConcurrentQueue<BazSparkCommand> _queue = new();

        /// <summary>Enqueue a command and raise the ExternalEvent.</summary>
        public void Enqueue(BazSparkCommand cmd)
        {
            _queue.Enqueue(cmd);
            Application.BazSparkEvent?.Raise();
        }

        public string GetName() => "BazSparkExternalEventHandler";

        /// <summary>
        /// Called by Revit on the main UI thread when the ExternalEvent is raised.
        /// Drains the queue and executes all pending commands.
        /// </summary>
        public void Execute(UIApplication uiApp)
        {
            while (_queue.TryDequeue(out var cmd))
            {
                try
                {
                    var result = DispatchCommand(uiApp, cmd);
                    cmd.ResultJson = JsonConvert.SerializeObject(
                        new { success = true, data = result });
                }
                catch (Exception ex)
                {
                    cmd.ResultJson = JsonConvert.SerializeObject(
                        new { success = false, error = ex.Message });
                }
                finally
                {
                    cmd.Done.Set(); // Signal the pipe server that we're done
                }
            }
        }

        // ────────────────────────────────────────────────────────────────────────
        // Command Dispatcher
        // ────────────────────────────────────────────────────────────────────────

        private object DispatchCommand(UIApplication uiApp, BazSparkCommand cmd)
        {
            var doc  = uiApp.ActiveUIDocument?.Document
                       ?? throw new InvalidOperationException("No active Revit document.");
            var p    = cmd.Params;

            return cmd.Action switch
            {
                // ── Document & Info ──────────────────────────────────────────
                "get_info" => new {
                    title = doc.Title,
                    path  = doc.PathName,
                    is_workshared = doc.IsWorkshared
                },

                "list_elements" => ListElements(doc, p),

                // ── Wall creation ────────────────────────────────────────────
                "create_wall" => CreateWall(doc, p),

                // ── Floor creation ───────────────────────────────────────────
                "create_floor" => CreateFloor(doc, p),

                // ── Door / Window insertion ──────────────────────────────────
                "place_family_instance" => PlaceFamilyInstance(doc, uiApp, p),

                // ── Element deletion ─────────────────────────────────────────
                "delete_element" => DeleteElement(doc, p),

                // ── Parameter read/write ─────────────────────────────────────
                "get_parameter" => GetParameter(doc, p),
                "set_parameter" => SetParameter(doc, p),

                // ── Views ────────────────────────────────────────────────────
                "list_views" => ListViews(doc),

                // ── Saving ───────────────────────────────────────────────────
                "save" => SaveDocument(doc),

                _ => throw new NotSupportedException($"Unknown action: {cmd.Action}")
            };
        }

        // ────────────────────────────────────────────────────────────────────────
        // Helpers
        // ────────────────────────────────────────────────────────────────────────

        private static object ListElements(Document doc, JObject p)
        {
            var categoryName = p["category"]?.ToString() ?? "";
            var collector = new FilteredElementCollector(doc).WhereElementIsNotElementType();

            if (!string.IsNullOrEmpty(categoryName) &&
                Enum.TryParse<BuiltInCategory>(categoryName, out var builtIn))
                collector = collector.OfCategory(builtIn);

            var elements = new List<object>();
            foreach (var el in collector)
            {
                elements.Add(new {
                    id       = el.Id.IntegerValue,
                    name     = el.Name,
                    category = el.Category?.Name ?? ""
                });
                if (elements.Count >= 500) break; // Safety cap
            }
            return new { count = elements.Count, elements };
        }

        private static object CreateWall(Document doc, JObject p)
        {
            using var tx = new Transaction(doc, "BazSpark: Create Wall");
            tx.Start();

            var x1 = p["x1"]?.Value<double>() ?? 0;
            var y1 = p["y1"]?.Value<double>() ?? 0;
            var x2 = p["x2"]?.Value<double>() ?? 5000;
            var y2 = p["y2"]?.Value<double>() ?? 0;
            var height = p["height"]?.Value<double>() ?? 3000;

            // Convert mm → feet (Revit internal unit)
            double mmToFt = 1.0 / 304.8;
            var line = Line.CreateBound(
                new XYZ(x1 * mmToFt, y1 * mmToFt, 0),
                new XYZ(x2 * mmToFt, y2 * mmToFt, 0));

            var levelId = new FilteredElementCollector(doc)
                .OfClass(typeof(Level))
                .FirstElementId();

            var wall = Wall.Create(doc, line, levelId, false);
            if (wall is null) throw new InvalidOperationException("Wall creation failed.");

            tx.Commit();
            return new { id = wall.Id.IntegerValue, length_mm = line.Length * 304.8 };
        }

        private static object CreateFloor(Document doc, JObject p)
        {
            using var tx = new Transaction(doc, "BazSpark: Create Floor");
            tx.Start();

            var coords = p["points"]?.ToObject<List<List<double>>>()
                         ?? new List<List<double>> { new() { 0, 0 }, new() { 5000, 0 },
                                                      new() { 5000, 5000 }, new() { 0, 5000 } };
            double mmToFt = 1.0 / 304.8;
            var curveLoop = new CurveLoop();
            for (int i = 0; i < coords.Count; i++)
            {
                var a = coords[i];
                var b = coords[(i + 1) % coords.Count];
                curveLoop.Append(Line.CreateBound(
                    new XYZ(a[0] * mmToFt, a[1] * mmToFt, 0),
                    new XYZ(b[0] * mmToFt, b[1] * mmToFt, 0)));
            }

            var floorType = new FilteredElementCollector(doc)
                .OfClass(typeof(FloorType))
                .FirstElement() as FloorType;

            var levelId = new FilteredElementCollector(doc)
                .OfClass(typeof(Level))
                .FirstElementId();

            var floor = Floor.Create(doc, new List<CurveLoop> { curveLoop },
                floorType!.Id, levelId);
            tx.Commit();
            return new { id = floor.Id.IntegerValue };
        }

        private static object PlaceFamilyInstance(Document doc, UIApplication uiApp, JObject p)
        {
            var familyName = p["family"]?.ToString() ?? "";
            var x = p["x"]?.Value<double>() ?? 0;
            var y = p["y"]?.Value<double>() ?? 0;
            double mmToFt = 1.0 / 304.8;

            var symbol = new FilteredElementCollector(doc)
                .OfClass(typeof(FamilySymbol))
                .OfType<FamilySymbol>()
                .FirstOrDefault(fs => fs.FamilyName.Contains(familyName))
                ?? throw new InvalidOperationException($"Family '{familyName}' not found.");

            using var tx = new Transaction(doc, "BazSpark: Place Family");
            tx.Start();
            if (!symbol.IsActive) symbol.Activate();
            var inst = doc.Create.NewFamilyInstance(
                new XYZ(x * mmToFt, y * mmToFt, 0),
                symbol,
                Autodesk.Revit.DB.Structure.StructuralType.NonStructural);
            tx.Commit();
            return new { id = inst.Id.IntegerValue };
        }

        private static object DeleteElement(Document doc, JObject p)
        {
            var id = new ElementId(p["id"]?.Value<int>() ?? 0);
            using var tx = new Transaction(doc, "BazSpark: Delete");
            tx.Start();
            doc.Delete(id);
            tx.Commit();
            return new { deleted_id = id.IntegerValue };
        }

        private static object GetParameter(Document doc, JObject p)
        {
            var id  = new ElementId(p["id"]?.Value<int>() ?? 0);
            var name = p["name"]?.ToString() ?? "";
            var el   = doc.GetElement(id) ?? throw new InvalidOperationException("Element not found.");
            var param = el.LookupParameter(name) ?? throw new InvalidOperationException($"Parameter '{name}' not found.");
            return new { name, value = param.AsValueString() };
        }

        private static object SetParameter(Document doc, JObject p)
        {
            var id   = new ElementId(p["id"]?.Value<int>() ?? 0);
            var name  = p["name"]?.ToString() ?? "";
            var value = p["value"]?.ToString() ?? "";
            var el    = doc.GetElement(id) ?? throw new InvalidOperationException("Element not found.");
            var param = el.LookupParameter(name) ?? throw new InvalidOperationException($"Parameter '{name}' not found.");

            using var tx = new Transaction(doc, "BazSpark: Set Parameter");
            tx.Start();
            param.SetValueString(value);
            tx.Commit();
            return new { updated = true };
        }

        private static object ListViews(Document doc)
        {
            var views = new List<object>();
            foreach (View v in new FilteredElementCollector(doc).OfClass(typeof(View)))
            {
                if (!v.IsTemplate)
                    views.Add(new { id = v.Id.IntegerValue, name = v.Name, type = v.ViewType.ToString() });
            }
            return new { count = views.Count, views };
        }

        private static object SaveDocument(Document doc)
        {
            if (string.IsNullOrEmpty(doc.PathName))
                return new { saved = false, reason = "Document has no path (unsaved new file)" };
            doc.Save();
            return new { saved = true, path = doc.PathName };
        }
    }
}
