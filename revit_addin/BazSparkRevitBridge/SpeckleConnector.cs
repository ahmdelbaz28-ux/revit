using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Autodesk.Revit.DB;
using Speckle.Core.Api;
using Speckle.Core.Credentials;
using Speckle.Core.Models;
using Speckle.Core.Transports;

namespace BazSparkRevitBridge
{
    public static class SpeckleConnector
    {
        /// <summary>
        /// Pulls the latest commit/version from the Speckle stream and returns the list of serialized objects.
        /// </summary>
        public static async Task<List<Base>> ReceiveModel(string streamId, string serverUrl, string token)
        {
            Account account = new Account
            {
                token = token,
                serverInfo = new ServerInfo { url = serverUrl }
            };

            using var client = new Client(account);
            
            // 1. Get the latest commit referenced object ID from the main branch
            var branch = await client.BranchGet(streamId, "main", 1);
            if (branch == null || branch.commits == null || branch.commits.items.Count == 0)
            {
                return new List<Base>();
            }

            string referencedObject = branch.commits.items[0].referencedObject;

            // 2. Receive the commit root object
            using var transport = new ServerTransport(account, streamId);
            Base commitRoot = await Operations.Receive(
                referencedObject,
                cancellationToken: default,
                remoteTransport: transport);

            if (commitRoot == null) return new List<Base>();

            // 3. Extract elements list from standard Speckle commit containers
            List<Base> elements = new List<Base>();
            var elementsProp = commitRoot["@elements"] ?? commitRoot["elements"];
            if (elementsProp is IEnumerable list)
            {
                foreach (var obj in list)
                {
                    if (obj is Base b)
                    {
                        elements.Add(b);
                    }
                }
            }

            return elements;
        }

        /// <summary>
        /// Builds Native Revit Family Instances from the Speckle elements list.
        /// Runs on Revit UI thread inside an active Transaction.
        /// </summary>
        public static int BuildElementsInRevit(Document doc, List<Base> elements)
        {
            int createdCount = 0;

            // 1. Retrieve default Level 1
            ElementId levelId = new FilteredElementCollector(doc)
                .OfClass(typeof(Level))
                .FirstElementId();

            double mmToFt = 1.0 / 304.8; // Convert mm (Speckle/AutoCAD) to feet (Revit internal unit)

            foreach (var elem in elements)
            {
                try
                {
                    string? type = elem["type"]?.ToString();
                    string? category = elem["category"]?.ToString();

                    // Read coordinates (x, y, z)
                    object? xObj = elem["x"] ?? elem["X"];
                    object? yObj = elem["y"] ?? elem["Y"];
                    object? zObj = elem["z"] ?? elem["Z"];

                    if (xObj != null && yObj != null)
                    {
                        double x = Convert.ToDouble(xObj) * mmToFt;
                        double y = Convert.ToDouble(yObj) * mmToFt;
                        double z = zObj != null ? Convert.ToDouble(zObj) * mmToFt : 0.0;

                        string familyName = type ?? "Fire Alarm Detector";
                        
                        // Find a FamilySymbol that contains the name
                        FamilySymbol? symbol = new FilteredElementCollector(doc)
                            .OfClass(typeof(FamilySymbol))
                            .OfType<FamilySymbol>()
                            .FirstOrDefault(fs => fs.FamilyName.Contains(familyName) || fs.Name.Contains(familyName));

                        // Fallback to first available family symbol if specific one not found
                        if (symbol == null)
                        {
                            symbol = new FilteredElementCollector(doc)
                                .OfClass(typeof(FamilySymbol))
                                .OfType<FamilySymbol>()
                                .FirstOrDefault();
                        }

                        if (symbol != null)
                        {
                            using (var tx = new Transaction(doc, "BazSpark: Speckle Element Creation"))
                            {
                                tx.Start();
                                
                                if (!symbol.IsActive) symbol.Activate();
                                var inst = doc.Create.NewFamilyInstance(
                                    new XYZ(x, y, z),
                                    symbol,
                                    Autodesk.Revit.DB.Structure.StructuralType.NonStructural);

                                tx.Commit();
                                
                                if (inst != null)
                                {
                                    createdCount++;
                                }
                            }
                        }
                    }
                }
                catch
                {
                    // Skip elements that fail to create
                }
            }

            return createdCount;
        }
    }
}
