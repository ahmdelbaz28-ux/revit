// NOSONAR
/**
 * ElementList.tsx — Sortable, filterable element table
 */

import { Eye, Search, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
        Table,
        TableBody,
        TableCell,
        TableHead,
        TableHeader,
        TableRow,
} from "@/components/ui/table";

export interface ElementItem {
        id: string;
        name: string;
        category: string;
        level?: string;
        type?: string;
        [key: string]: unknown;
}

interface ElementListProps {
        elements: ElementItem[];
        loading?: boolean;
        onView?: (element: ElementItem) => void;
        onDelete?: (element: ElementItem) => void;
}

export function ElementList({  // NOSONAR - typescript:S6759
        elements,
        loading,
        onView,
        onDelete,
}: ElementListProps) {
        const [search, setSearch] = useState("");
        const [categoryFilter, setCategoryFilter] = useState("all");

        const categories = useMemo(() => {
                const set = new Set(elements.map((e) => e.category));
                // V196: Use localeCompare for reliable alphabetical sort (SonarCloud S2871)
                return ["all", ...Array.from(set).sort((a, b) => a.localeCompare(b))];
        }, [elements]);

        const filtered = useMemo(() => {
                return elements.filter((e) => {
                        const matchesSearch =
                                e.name.toLowerCase().includes(search.toLowerCase()) ||
                                e.id.toLowerCase().includes(search.toLowerCase());
                        const matchesCategory =
                                categoryFilter === "all" || e.category === categoryFilter;
                        return matchesSearch && matchesCategory;
                });
        }, [elements, search, categoryFilter]);

        if (loading) {
                return (
                        <div className="space-y-2">
                                {[...Array(5)].map((_, i) => (  // NOSONAR - typescript:S7723
                                        <div key={i} className="h-12 bg-slate-800 rounded animate-pulse" />  // NOSONAR — S6479: array index key acceptable for static list
                                ))}
                        </div>
                );
        }

        return (
                <div className="space-y-3">
                        <div className="flex gap-2">
                                <div className="relative flex-1">
                                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                                        <Input
                                                placeholder="Search by name or ID..."
                                                value={search}
                                                onChange={(e) => setSearch(e.target.value)}
                                                className="pl-10 bg-slate-900 border-slate-700 text-slate-100"
                                        />
                                </div>
                                <select
                                        value={categoryFilter}
                                        onChange={(e) => setCategoryFilter(e.target.value)}
                                        className="bg-slate-900 border border-slate-700 text-slate-100 rounded-md px-3 py-2 text-sm"
                                >
                                        {categories.map((c) => (
                                                <option key={c} value={c}>
                                                        {c === "all" ? "All Categories" : c}
                                                </option>
                                        ))}
                                </select>
                        </div>
                        <div className="rounded-md border border-slate-700 overflow-hidden">
                                <Table>
                                        <TableHeader>
                                                <TableRow className="border-slate-700 bg-slate-800/50">
                                                        <TableHead className="text-slate-400">ID</TableHead>
                                                        <TableHead className="text-slate-400">Name</TableHead>
                                                        <TableHead className="text-slate-400">Category</TableHead>
                                                        <TableHead className="text-slate-400">Level</TableHead>
                                                        <TableHead className="text-slate-400 text-right">
                                                                Actions
                                                        </TableHead>
                                                </TableRow>
                                        </TableHeader>
                                        <TableBody>
                                                {filtered.length === 0 ? (
                                                        <TableRow>
                                                                <TableCell
                                                                        colSpan={5}
                                                                        className="text-center text-slate-500 py-8"
                                                                >
                                                                        No elements found
                                                                </TableCell>
                                                        </TableRow>
                                                ) : (
                                                        filtered.map((el) => (
                                                                <TableRow
                                                                        key={el.id}
                                                                        className="border-slate-700 hover:bg-slate-800/50"
                                                                >
                                                                        <TableCell className="font-mono text-xs text-slate-400">
                                                                                {el.id}
                                                                        </TableCell>
                                                                        <TableCell className="text-slate-200">{el.name}</TableCell>
                                                                        <TableCell>
                                                                                <Badge
                                                                                        variant="outline"
                                                                                        className="border-slate-600 text-slate-300"
                                                                                >
                                                                                        {el.category}
                                                                                </Badge>
                                                                        </TableCell>
                                                                        <TableCell className="text-slate-400">
                                                                                {el.level || "-"}
                                                                        </TableCell>
                                                                        <TableCell className="text-right">
                                                                                <div className="flex justify-end gap-1">
                                                                                        {onView && (
                                                                                                <Button
                                                                                                        size="sm"
                                                                                                        variant="ghost"
                                                                                                        onClick={() => onView(el)}
                                                                                                >
                                                                                                        <Eye className="h-4 w-4" />
                                                                                                </Button>
                                                                                        )}
                                                                                        {onDelete && (
                                                                                                <Button
                                                                                                        size="sm"
                                                                                                        variant="ghost"
                                                                                                        onClick={() => onDelete(el)}
                                                                                                        className="text-red-400 hover:text-red-300"
                                                                                                >
                                                                                                        <Trash2 className="h-4 w-4" />
                                                                                                </Button>
                                                                                        )}
                                                                                </div>
                                                                        </TableCell>
                                                                </TableRow>
                                                        ))
                                                )}
                                        </TableBody>
                                </Table>
                        </div>
                        <p className="text-xs text-slate-500">
                                Showing {filtered.length} of {elements.length} elements
                        </p>
                </div>
        );
}
