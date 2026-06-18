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
using System.Threading;
using System.Threading.Channels;
using Autodesk.Revit.UI;
using Autodesk.Revit.DB;

namespace FireAI.RevitAddin
{
    /// <summary>
    /// Thread-safe queue handler for Revit model updates.
    /// Implements IExternalEventHandler to ensure all model writes
    /// occur on the Revit UI thread.
    ///
    /// v2 (2026-06-18):
    ///   - Uses BoundedChannel&lt;T&gt; instead of Queue&lt;T&gt; + manual size
    ///     check. The Channel handles capacity atomically, eliminating the
    ///     race between Count check and Enqueue that v1 had.
    ///   - BatchSize is opt-in (default = 1) — preserves v1 semantics of
    ///     one-transaction-per-action. Set higher (e.g. 50) for throughput
    ///     at the cost of weaker per-action isolation. v1 review incorrectly
    ///     forced batching=50 by default, which was a behavior change.
    ///   - Dropped unnecessary Interlocked on _processedCount / _failedCount
    ///     — those are mutated only on the Revit UI thread (single-threaded).
    ///     Only _droppedCount needs Interlocked (mutated from any producer thread).
    /// </summary>
    public class ThreadSafeQueueHandler : IExternalEventHandler
    {
        // BoundedChannel<T> provides thread-safe enqueue/dequeue with a hard
        // capacity limit. When full, TryWrite returns false atomically — no
        // race window between the size check and the write.
        private readonly Channel<Action<UIApplication>> _channel;

        // Mutated ONLY on Revit UI thread (Execute is called by Revit's
        // ExternalEvent system on the UI thread). No Interlocked needed.
        private int _processedCount = 0;
        private int _failedCount = 0;

        // Mutated from any producer thread (EnqueueAction callers).
        // Interlocked required.
        private int _droppedCount = 0;

        /// <summary>
        /// Maximum number of actions processed in a single Execute call.
        /// Default = 1 preserves v1 behavior (one transaction per action).
        /// Set to a higher value (e.g. 50) to amortize transaction overhead
        /// when the queue is drained after a burst of MCP requests. Higher
        /// values mean a single failed action does NOT roll back other
        /// actions in the same batch — each action's exception is caught
        /// and the batch continues.
        /// </summary>
        public int BatchSize { get; set; } = 1;

        /// <summary>
        /// Create a new handler with the given queue capacity.
        /// </summary>
        /// <param name="capacity">
        /// Maximum number of pending actions. When full, EnqueueAction
        /// returns false and increments DroppedCount. Default = 10,000.
        /// </param>
        public ThreadSafeQueueHandler(int capacity = 10_000)
        {
            if (capacity < 1)
                throw new ArgumentOutOfRangeException(
                    nameof(capacity), "capacity must be at least 1");

            _channel = Channel.CreateBounded<Action<UIApplication>>(
                new BoundedChannelOptions(capacity)
                {
                    // Drop the new write when full; caller learns via TryWrite=false.
                    FullMode = BoundedChannelFullMode.DropWrite,
                    // Revit UI thread is the only reader.
                    SingleReader = true,
                    // Any thread (MCP server workers) can write.
                    SingleWriter = false,
                }
            );
        }

        /// <summary>
        /// Enqueue an action for safe execution on the Revit UI thread.
        /// Thread-safe: can be called from any thread.
        /// </summary>
        /// <param name="action">
        /// Action that modifies the Revit model.
        /// The action receives a UIApplication for model access.
        /// </param>
        /// <returns>
        /// True if the action was enqueued; false if the queue was full
        /// (action dropped, DroppedCount incremented).
        /// </returns>
        public bool EnqueueAction(Action<UIApplication> action)
        {
            if (action == null)
                throw new ArgumentNullException(
                    nameof(action),
                    "Cannot enqueue null action. " +
                    "[FireAI Safety: All model updates must have a defined action.]");

            if (_channel.Writer.TryWrite(action))
                return true;

            // Queue is full — record the drop and return false so the
            // caller can apply back-pressure.
            Interlocked.Increment(ref _droppedCount);
            System.Diagnostics.Debug.WriteLine(
                $"[FireAI SAFETY WARNING]: Action queue full. " +
                $"Action dropped. Total dropped: {_droppedCount}. " +
                $"This indicates the Revit UI thread cannot keep up with MCP requests.");
            return false;
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

            Document doc = app.ActiveUIDocument?.Document;
            if (doc == null)
            {
                // Drain the queue so we don't accumulate actions while no
                // document is open. Without this, the queue fills up and
                // every subsequent EnqueueAction returns false.
                int droppedHere = 0;
                while (_channel.Reader.TryRead(out _))
                    droppedHere++;
                if (droppedHere > 0)
                {
                    _failedCount += droppedHere;
                    System.Diagnostics.Debug.WriteLine(
                        $"[FATAL ENGINE ERROR]: No active Revit document. " +
                        $"Dropped {droppedHere} pending actions. " +
                        $"Total failed: {_failedCount}.");
                }
                return;
            }

            // Process up to BatchSize actions in one transaction.
            // Default BatchSize=1 preserves v1's per-action isolation.
            int remaining = BatchSize;
            using (Transaction trans = new Transaction(doc, "FireAI Safe BIM Update"))
            {
                trans.Start();
                try
                {
                    while (remaining > 0 &&
                           _channel.Reader.TryRead(out Action<UIApplication> actionToExecute))
                    {
                        try
                        {
                            actionToExecute(app);
                            _processedCount++;
                        }
                        catch (Autodesk.Revit.Exceptions.InvalidObjectStateException ex)
                        {
                            // Revit API specific error — model element no longer valid.
                            // Skip this action, continue the batch.
                            _failedCount++;
                            System.Diagnostics.Debug.WriteLine(
                                $"[FATAL ENGINE ERROR]: Invalid Revit object state: {ex.Message}. " +
                                $"Action skipped, batch continues. Total failed: {_failedCount}.");
                        }
                        catch (Autodesk.Revit.Exceptions.ArgumentException ex)
                        {
                            // Invalid parameter value written to Revit element.
                            _failedCount++;
                            System.Diagnostics.Debug.WriteLine(
                                $"[FATAL ENGINE ERROR]: Invalid parameter value: {ex.Message}. " +
                                $"Action skipped, batch continues. Total failed: {_failedCount}.");
                        }
                        catch (Exception ex)
                        {
                            // General error — skip this action, continue the batch.
                            _failedCount++;
                            System.Diagnostics.Debug.WriteLine(
                                $"[FATAL ENGINE ERROR]: Model update failed: {ex.Message}. " +
                                $"Action skipped, batch continues. Total failed: {_failedCount}.");
                        }
                        remaining--;
                    }

                    if (trans.HasStarted() && !trans.HasEnded())
                    {
                        trans.Commit();
                    }
                }
                catch (Exception ex)
                {
                    // Transaction-level failure (not per-action). Roll back.
                    if (trans.HasStarted() && !trans.HasEnded())
                        trans.RollBack();
                    System.Diagnostics.Debug.WriteLine(
                        $"[FATAL ENGINE ERROR]: Transaction-level failure: {ex.Message}. " +
                        $"Transaction rolled back.");
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
        public int PendingCount => _channel.Reader.Count;

        /// <summary>
        /// Get processing statistics.
        /// </summary>
        public (int Processed, int Failed, int Dropped) GetStats() =>
            (_processedCount, _failedCount, _droppedCount);
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
