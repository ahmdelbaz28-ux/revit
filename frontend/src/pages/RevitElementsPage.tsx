/**
 * RevitElementsPage.tsx — View and manage Revit elements
 */
import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { RefreshCw, Eye, Trash2 } from 'lucide-react';
import { revitService } from '@/services/revitService';
import { ElementList, type ElementItem } from '@/components/shared/ElementList';
import { toast } from 'sonner';

export function RevitElementsPage() {
  const [elements, setElements] = useState<ElementItem[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchElements = useCallback(async () => {
    setLoading(true);
    try {
      const result = await revitService.getElements();
      const items = Array.isArray(result) ? result : (result as { elements?: unknown[] })?.elements || [];
      setElements(items as ElementItem[]);
    } catch (err) {
      toast.error(`Failed to load elements: ${err instanceof Error ? err.message : 'Unknown error'}`);
      setElements([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchElements(); }, [fetchElements]);

  const handleView = (el: ElementItem) => {
    toast.info(`Viewing element: ${el.name} (${el.id})`);
  };

  const handleDelete = async (el: ElementItem) => {
    try {
      await revitService.deleteElement(el.id);
      toast.success(`Deleted element: ${el.name}`);
      fetchElements();
    } catch (err) {
      toast.error(`Delete failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  };

  return (
    <div className="flex-1 overflow-auto p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Revit Elements</h1>
          <p className="text-sm text-slate-400 mt-1">View, filter, and manage Revit elements</p>
        </div>
        <Button onClick={fetchElements} variant="outline" className="border-slate-600 text-slate-300">
          <RefreshCw className="h-4 w-4 mr-2" /> Refresh
        </Button>
      </div>
      <Card className="border-slate-700 bg-slate-800/80">
        <CardHeader>
          <CardTitle className="text-slate-100">Elements ({elements.length})</CardTitle>
        </CardHeader>
        <CardContent>
          <ElementList elements={elements} loading={loading} onView={handleView} onDelete={handleDelete} />
        </CardContent>
      </Card>
    </div>
  );
}
