/// <summary>
/// ThreadSafeQueueHandler.cs — Reference Implementation for Revit IExternalEventHandler
/// ================================================================================
/// LIFE-SAFETY CRITICAL: This C# class MUST be used as the companion to the
/// Python ThreadSafeModelUpdateQueue. It runs on the Revit UI thread and
/// processes all model update actions that were enqueued by the MCP server.
///
/// ARCHITECTURE:
///   Python MCP Server → ThreadSafeModelUpdateQueue (Python)
///   ↕ (shared state via file/pipe/socket)
///   C# Revit Add-in → ThreadSafeQueueHandler : IExternalEventHandler
///   → Executes on Revit UI thread inside Transaction
///
/// FORENSIC AUDIT REFERENCE:
///   Finding 1: Unsafe Multithreading on Revit API (Catastrophic)
///   Root Cause: MCP server called Revit API from background thread
///   Fix: All model writes must go through IExternalEventHandler
///
/// STANDARDS:
///   - Revit API SDK Concurrency Guidelines
///   - ISO 17822 (Software Quality in Building Engineering)
///   - NFPA 13-2022 Chapter 23 (Hydraulic Calculations)
///
/// INTEGRATION STEPS:
///   1. Add this class to your Revit add-in project
///   2. Register with Revit's ExternalEvent system during startup:
///      var handler = new ThreadSafeQueueHandler();
///      var externalEvent = ExternalEvent.Create(handler);
///   3. When the Python MCP server enqueues an action, signal Revit:
///      externalEvent.Raise()
///   4. Revit calls handler.Execute() on the UI thread
///   5. The handler dequeues and executes the action in a Transaction
///
/// Communication between Python and C# can use:
///   - Named pipes (recommended for real-time)
///   - Shared SQLite database (simple, reliable)
///   - TCP socket (cross-platform)
///   - JSON file on disk (simplest, but slowest)
/// </summary>

using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.Revit.UI;
using Autodesk.Revit.DB;

namespace FireAI.RevitAddin
{
    /// <summary>
    /// Thread-safe queue handler for Revit model updates.
    /// Implements IExternalEventHandler to ensure all model writes
    /// occur on the Revit UI thread.
    /// </summary>
    public class ThreadSafeQueueHandler : IExternalEventHandler
    {
        private readonly Queue<Action<UIApplication>> _actionQueue
            = new Queue<Action<UIApplication>>();
        private readonly object _lockObj = new object();
        private int _processedCount = 0;
        private int _failedCount = 0;

        /// <summary>
        /// Enqueue an action for safe execution on the Revit UI thread.
        /// Thread-safe: can be called from any thread.
        /// </summary>
        /// <param name="action">
        /// Action that modifies the Revit model.
        /// The action receives a UIApplication for model access.
        /// </param>
        public void EnqueueAction(Action<UIApplication> action)
        {
            if (action == null)
                throw new ArgumentNullException(nameof(action),
                    "Cannot enqueue null action. " +
                    "[FireAI Safety: All model updates must have a defined action.]");

            lock (_lockObj)
            {
                _actionQueue.Enqueue(action);
            }
        }

        /// <summary>
        /// Execute pending actions on the Revit UI thread.
        /// Called by Revit's ExternalEvent system.
        /// </summary>
        /// <param name="app">UIApplication provided by Revit.</param>
        public void Execute(UIApplication app)
        {
            if (app == null)
            {
                // SAFETY: Cannot proceed without valid UIApplication
                System.Diagnostics.Debug.WriteLine(
                    "[FATAL ENGINE ERROR]: Execute called with null UIApplication. " +
                    "This should never happen — Revit API contract violation.");
                return;
            }

            Action<UIApplication> actionToExecute = null;

            lock (_lockObj)
            {
                if (_actionQueue.Count > 0)
                {
                    actionToExecute = _actionQueue.Dequeue();
                }
            }

            if (actionToExecute == null)
                return; // No pending actions

            // Execute the action inside a Transaction for atomicity
            Document doc = app.ActiveUIDocument?.Document;
            if (doc == null)
            {
                System.Diagnostics.Debug.WriteLine(
                    "[FATAL ENGINE ERROR]: No active Revit document. " +
                    "Cannot execute model update. Action discarded.");
                _failedCount++;
                return;
            }

            using (Transaction trans = new Transaction(doc,
                "FireAI Safe BIM Thread Update"))
            {
                trans.Start();
                try
                {
                    actionToExecute(app);

                    // Validate transaction before commit
                    if (trans.HasStarted() && !trans.HasEnded())
                    {
                        trans.Commit();
                        _processedCount++;
                        System.Diagnostics.Debug.WriteLine(
                            $"[FireAI]: Model update committed successfully. " +
                            $"Total processed: {_processedCount}");
                    }
                }
                catch (Autodesk.Revit.Exceptions.InvalidObjectStateException ex)
                {
                    // Revit API specific error — model element no longer valid
                    if (trans.HasStarted() && !trans.HasEnded())
                        trans.RollBack();
                    _failedCount++;
                    System.Diagnostics.Debug.WriteLine(
                        $"[FATAL ENGINE ERROR]: Invalid Revit object state: {ex.Message}. " +
                        $"Transaction rolled back. Total failed: {_failedCount}");
                }
                catch (Autodesk.Revit.Exceptions.ArgumentException ex)
                {
                    // Invalid parameter value written to Revit element
                    if (trans.HasStarted() && !trans.HasEnded())
                        trans.RollBack();
                    _failedCount++;
                    System.Diagnostics.Debug.WriteLine(
                        $"[FATAL ENGINE ERROR]: Invalid parameter value: {ex.Message}. " +
                        $"Check that MCP-sent values are within Revit parameter bounds. " +
                        $"Transaction rolled back. Total failed: {_failedCount}");
                }
                catch (Exception ex)
                {
                    // General error — always roll back for safety
                    if (trans.HasStarted() && !trans.HasEnded())
                        trans.RollBack();
                    _failedCount++;
                    System.Diagnostics.Debug.WriteLine(
                        $"[FATAL ENGINE ERROR]: Model update failed: {ex.Message}. " +
                        $"Transaction rolled back. Total failed: {_failedCount}. " +
                        $"This may indicate a safety-critical issue in the MCP pipeline.");
                }
            }
        }

        /// <summary>
        /// Required by IExternalEventHandler interface.
        /// Returns the handler name for Revit's event system.
        /// </summary>
        public string GetName() => "ThreadSafeQueueHandler";

        /// <summary>
        /// Get the number of pending actions in the queue.
        /// </summary>
        public int PendingCount
        {
            get
            {
                lock (_lockObj)
                {
                    return _actionQueue.Count;
                }
            }
        }

        /// <summary>
        /// Get processing statistics.
        /// </summary>
        public (int Processed, int Failed) GetStats() => (_processedCount, _failedCount);
    }


    /// <summary>
    /// Helper class for creating common model update actions.
    /// These factory methods ensure that all updates follow the
    /// correct pattern and use validated parameters.
    /// </summary>
    public static class ModelUpdateActions
    {
        /// <summary>
        /// Create an action that sets a parameter on a Revit element.
        /// SAFETY: Parameter value must be pre-validated by the Python
        /// SanitizedMCPHandler before calling this method.
        /// </summary>
        public static Action<UIApplication> SetParameter(
            string elementId,
            string parameterName,
            double value,
            string nfpaReference = "")
        {
            return (app) =>
            {
                Document doc = app.ActiveUIDocument.Document;

                // SAFETY: Validate element ID before parsing
                if (!int.TryParse(elementId, out int elemIdInt))
                    throw new ArgumentException(
                        $"Invalid element ID: '{elementId}'. Must be an integer. " +
                        "[FireAI Safety: Prevents crash from malformed MCP input.]");

                Element elem = doc.GetElement(new ElementId(elemIdInt));

                if (elem == null)
                    throw new InvalidOperationException(
                        $"Element {elementId} not found in Revit document. " +
                        "Cannot update parameter.");

                // SAFETY: Try Guid parse first; fall back to BuiltInParameter lookup
                // for human-readable parameter names (e.g., "Diameter", "Hazard Class")
                Parameter param = null;
                if (Guid.TryParse(parameterName, out Guid paramGuid))
                {
                    param = elem.get_Parameter(paramGuid);
                }
                else
                {
                    // Try BuiltInParameter enum lookup for known parameter names
                    BuiltInParameter bip;
                    if (Enum.TryParse(parameterName, out bip))
                    {
                        param = elem.get_Parameter(bip);
                    }
                    else
                    {
                        // Fall back to case-insensitive name lookup
                        param = elem.LookupParameter(parameterName);
                    }
                }

                if (param == null)
                    throw new InvalidOperationException(
                        $"Parameter '{parameterName}' not found on element {elementId}. " +
                        "Check that the parameter exists and is writable.");

                if (param.IsReadOnly)
                    throw new InvalidOperationException(
                        $"Parameter '{parameterName}' on element {elementId} is read-only. " +
                        "Fire safety parameters must be writable for compliance updates.");

                param.Set(value);
            };
        }

        /// <summary>
        /// Create an action that sets a string parameter on a Revit element.
        /// </summary>
        public static Action<UIApplication> SetStringParameter(
            string elementId,
            string parameterName,
            string value,
            string nfpaReference = "")
        {
            return (app) =>
            {
                Document doc = app.ActiveUIDocument.Document;

                if (!int.TryParse(elementId, out int elemIdInt))
                    throw new ArgumentException(
                        $"Invalid element ID: '{elementId}'. Must be an integer.");

                Element elem = doc.GetElement(new ElementId(elemIdInt));

                if (elem == null)
                    throw new InvalidOperationException(
                        $"Element {elementId} not found.");

                // Use same safe parameter lookup as SetParameter
                Parameter param = null;
                if (Guid.TryParse(parameterName, out Guid paramGuid))
                {
                    param = elem.get_Parameter(paramGuid);
                }
                else
                {
                    BuiltInParameter bip;
                    if (Enum.TryParse(parameterName, out bip))
                        param = elem.get_Parameter(bip);
                    else
                        param = elem.LookupParameter(parameterName);
                }

                if (param == null)
                    throw new InvalidOperationException(
                        $"Parameter '{parameterName}' not found.");

                param.Set(value);
            };
        }
    }
}
