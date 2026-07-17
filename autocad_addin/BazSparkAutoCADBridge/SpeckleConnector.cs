using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Speckle.Core.Api;
using Speckle.Core.Credentials;
using Speckle.Core.Models;
using Speckle.Core.Transports;
using Objects.Geometry;

namespace BazSparkAutoCADBridge
{
    public static class SpeckleConnector
    {
        /// <summary>
        /// Scans active AutoCAD drawing entities, converts them, and pushes them to the Speckle Server.
        /// </summary>
        public static async Task<string> PushModel(Document doc, string streamId, string serverUrl, string token)
        {
            Database db = doc.Database;
            List<Base> speckleObjects = new List<Base>();

            // 1. Gather and convert CAD entities inside a read-only transaction
            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                BlockTable bt = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
                BlockTableRecord btr = (BlockTableRecord)tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForRead);

                foreach (ObjectId id in btr)
                {
                    Entity ent = (Entity)tr.GetObject(id, OpenMode.ForRead);
                    if (!ent.Visible) continue;

                    Base? spObj = ConvertToSpeckle(ent);
                    if (spObj != null)
                    {
                        // Add metadata properties
                        spObj["layer"] = ent.Layer;
                        spObj["color"] = ent.ColorIndex;
                        spObj["handle"] = ent.Handle.ToString();
                        speckleObjects.Add(spObj);
                    }
                }
                tr.Commit();
            }

            if (speckleObjects.Count == 0)
            {
                throw new InvalidOperationException("No valid geometric entities found to send to Speckle.");
            }

            // 2. Configure Speckle account
            Account account = new Account
            {
                token = token,
                serverInfo = new ServerInfo { url = serverUrl }
            };

            // 3. Create root Speckle commit object
            Base commitRoot = new Base();
            commitRoot["@elements"] = speckleObjects;

            // 4. Send payload to Speckle server transport (explicit cancellation token for signature resolution)
            using var transport = new ServerTransport(account, streamId);
            string objectId = await Operations.Send(
                commitRoot,
                cancellationToken: default,
                transports: new List<ITransport> { transport },
                disposeTransports: true);

            // 5. Create a version/commit on the Speckle stream
            using var client = new Client(account);
            string commitId = await client.CommitCreate(new CommitCreateInput
            {
                streamId = streamId,
                objectId = objectId,
                branchName = "main",
                message = $"BAZspark: AutoCAD drawing sync - {speckleObjects.Count} elements",
                sourceApplication = "AutoCAD"
            });

            return commitId;
        }

        private static Base? ConvertToSpeckle(Entity ent)
        {
            if (ent is Autodesk.AutoCAD.DatabaseServices.Line line)
            {
                Point3d s = line.StartPoint;
                Point3d e = line.EndPoint;

                Point spStart = new Point(s.X, s.Y, s.Z, "mm");
                Point spEnd = new Point(e.X, e.Y, e.Z, "mm");

                return new Objects.Geometry.Line(spStart, spEnd, "mm")
                {
                    applicationId = line.Handle.ToString()
                };
            }
            else if (ent is Autodesk.AutoCAD.DatabaseServices.Circle circle)
            {
                Point c = new Point(circle.Center.X, circle.Center.Y, circle.Center.Z, "mm");
                
                // Represent AutoCAD circle in Speckle (Plane, radius) using fully qualified Objects.Geometry.Plane
                Objects.Geometry.Plane plane = new Objects.Geometry.Plane(
                    c,
                    new Vector(circle.Normal.X, circle.Normal.Y, circle.Normal.Z),
                    new Vector(1, 0, 0), // X dir
                    new Vector(0, 1, 0), // Y dir
                    "mm");

                return new Objects.Geometry.Circle(plane, circle.Radius, "mm")
                {
                    applicationId = circle.Handle.ToString()
                };
            }
            else if (ent is Autodesk.AutoCAD.DatabaseServices.Polyline poly)
            {
                // Convert lightweight polyline vertices
                List<double> coords = new List<double>();
                for (int i = 0; i < poly.NumberOfVertices; i++)
                {
                    Point2d pt = poly.GetPoint2dAt(i);
                    coords.Add(pt.X);
                    coords.Add(pt.Y);
                    coords.Add(0.0);
                }

                Polycurve polycurve = new Polycurve("mm");
                // Fall back to a standard Speckle representation of lines
                polycurve["segments"] = coords;
                polycurve.applicationId = poly.Handle.ToString();
                return polycurve;
            }

            return null; // Ignore unsupported entities for simplicity
        }
    }
}
