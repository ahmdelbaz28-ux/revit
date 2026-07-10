
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import {
        Select,
        SelectContent,
        SelectItem,
        SelectTrigger,
        SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/services/api";
import type {
        Element,
        ElementGeometryCreate,
        ElementPropertiesCreate,
} from "@/types";

// V187 FIX: ELEMENT_TYPES now includes translation keys so the dropdown
// shows translated text in Arabic mode instead of hardcoded English.
const ELEMENT_TYPES = [
        { value: "wall", labelKey: "elements.typeWall" },
        { value: "door", labelKey: "elements.typeDoor" },
        { value: "window", labelKey: "elements.typeWindow" },
        { value: "room", labelKey: "elements.typeRoom" },
        { value: "equipment", labelKey: "elements.typeEquipment" },
        { value: "mechanical", labelKey: "elements.typeMechanical" },
        { value: "electrical", labelKey: "elements.typeElectrical" },
        { value: "unknown", labelKey: "elements.typeUnknown" },
] as const;

const PAGE_SIZE = 20;

function Elements() {
        const { t } = useTranslation();
        const queryClient = useQueryClient();
        const [page, setPage] = useState(1);
        const [typeFilter, setTypeFilter] = useState<string>("");
        const [showCreateModal, setShowCreateModal] = useState(false);
        const [deleteTarget, setDeleteTarget] = useState<Element | null>(null);

        // Fetch elements
        const { data, isLoading, error } = useQuery({
                queryKey: ["elements", page, typeFilter],
                queryFn: () =>
                        api.getElements({
                                page,
                                page_size: PAGE_SIZE,
                                element_type: typeFilter || undefined,
                        }),
        });

        // Delete mutation
        const deleteMutation = useMutation({
                mutationFn: (id: string) => api.deleteElement(id),
                onSuccess: () => {
                        queryClient.invalidateQueries({ queryKey: ["elements"] });
                        setDeleteTarget(null);
                },
        });

        const totalPages = data?.items ? Math.ceil(data.total / PAGE_SIZE) : 1;

        // V207 FIX: Defensive check — data.items may be undefined if the API returns
        // an unexpected shape (e.g., empty array instead of { items: [], total: 0 }).
        // Without this, items.length throws TypeError → Error Boundary → page crash.
        const items = data?.items ?? [];

        return (
                <div className="space-y-6" aria-label={t("elements.title")}>
                        {/* Header */}
                        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                                <div>
                                        <h1 className="text-2xl font-bold text-white">
                                                {t("elements.title")}
                                        </h1>
                                        <p className="text-muted-foreground text-sm mt-1">
                                                {data
                                                        ? t("elements.totalElements", { count: data?.total ?? 0 })
                                                        : t("common.loading")}
                                        </p>
                                </div>
                                <button
                                        onClick={() => setShowCreateModal(true)}
                                        className="inline-flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary text-white text-sm font-medium rounded-lg transition-colors"
                                >
                                        <svg
                                                width="16"
                                                height="16"
                                                viewBox="0 0 24 24"
                                                fill="none"
                                                stroke="currentColor"
                                                strokeWidth="2"
                                                strokeLinecap="round"
                                                strokeLinejoin="round"
                                        >
                                                <line x1="12" y1="5" x2="12" y2="19" />
                                                <line x1="5" y1="12" x2="19" y2="12" />
                                        </svg>
                                        {t("elements.createElement")}
                                </button>
                        </div>

                        {/* Filters */}
                        <div className="flex flex-wrap items-center gap-3">
                                <select
                                        value={typeFilter}
                                        onChange={(e) => {
                                                setTypeFilter(e.target.value);
                                                setPage(1);
                                        }}
                                        className="bg-card border border-border text-white text-sm rounded-lg px-3 py-2 focus:border-primary focus:outline-none"
                                >
                                        <option value="">{t("elements.allTypes")}</option>
                                        {ELEMENT_TYPES.map((type) => (
                                                <option key={type.value} value={type.value}>
                                                        {t(type.labelKey)}
                                                </option>
                                        ))}
                                </select>
                                {typeFilter && (
                                        <Button
                                                variant="ghost"
                                                onClick={() => {
                                                        setTypeFilter("");
                                                        setPage(1);
                                                }}
                                                className="text-sm text-muted-foreground hover:text-white p-0 h-auto"
                                        >
                                                ✕ {t("common.clearFilter")}
                                        </Button>
                                )}
                        </div>

                        {/* Error */}
                        {error && (
                                <div className="bg-slate-500/10 border border-slate-500/20 rounded-lg p-4">
                                        <p className="text-danger text-sm">{t("elements.failedToLoad")}</p>
                                </div>
                        )}

                        {/* Loading */}
                        {isLoading && (
                                <div className="flex items-center justify-center py-12">
                                        <div className="w-8 h-8 border-2 border-border border-t-orange-500 rounded-full animate-spin" />
                                </div>
                        )}

                        {/* Table */}
                        {data && !isLoading && (
                                <>
                                        <div className="bg-card border border-border rounded-md overflow-hidden">
                                                <div className="overflow-x-auto">
                                                        <table
                                                                className="w-full text-sm"
                                                                aria-label={t("elements.title")}
                                                        >
                                                                <thead>
                                                                        <tr className="border-b border-border bg-muted/50">
                                                                                <th
                                                                                        scope="col"
                                                                                        className="text-left text-muted-foreground font-medium px-4 py-3"
                                                                                >
                                                                                        {t("elements.name")}
                                                                                </th>
                                                                                <th
                                                                                        scope="col"
                                                                                        className="text-left text-muted-foreground font-medium px-4 py-3"
                                                                                >
                                                                                        {t("elements.type")}
                                                                                </th>
                                                                                <th
                                                                                        scope="col"
                                                                                        className="text-left text-muted-foreground font-medium px-4 py-3"
                                                                                >
                                                                                        {t("elements.area")}
                                                                                </th>
                                                                                <th
                                                                                        scope="col"
                                                                                        className="text-left text-muted-foreground font-medium px-4 py-3"
                                                                                >
                                                                                        {t("elements.version")}
                                                                                </th>
                                                                                <th
                                                                                        scope="col"
                                                                                        className="text-left text-muted-foreground font-medium px-4 py-3"
                                                                                >
                                                                                        {t("elements.modified")}
                                                                                </th>
                                                                                <th
                                                                                        scope="col"
                                                                                        className="text-right text-muted-foreground font-medium px-4 py-3"
                                                                                >
                                                                                        {t("elements.actions")}
                                                                                </th>
                                                                        </tr>
                                                                </thead>
                                                                <tbody>
                                                                        {items.length === 0 ? (
                                                                                <tr>
                                                                                        <td colSpan={6} className="py-8">
                                                                                                <EmptyState
                                                                                                        icon={
                                                                                                                <svg
                                                                                                                        width="48"
                                                                                                                        height="48"
                                                                                                                        viewBox="0 0 24 24"
                                                                                                                        fill="none"
                                                                                                                        stroke="currentColor"
                                                                                                                        strokeWidth="1.5"
                                                                                                                        className="h-12 w-12 text-muted-foreground/70"
                                                                                                                >
                                                                                                                        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                                                                                                                </svg>
                                                                                                        }
                                                                                                        title={t("elements.noElements")}
                                                                                                        description={t("elements.createFirstElement")}
                                                                                                />
                                                                                        </td>
                                                                                </tr>
                                                                        ) : (
                                                                                items.map((element) => (
                                                                                        <tr
                                                                                                key={element.element_id}
                                                                                                className="border-b border-border/50 hover:bg-secondary/30 transition-colors"
                                                                                        >
                                                                                                <td className="px-4 py-3">
                                                                                                        <Link
                                                                                                                to={`/elements/${element.element_id}`}
                                                                                                                className="text-white hover:text-primary font-medium transition-colors"
                                                                                                        >
                                                                                                                {element.properties?.name ?? "Unnamed"}
                                                                                                        </Link>
                                                                                                </td>
                                                                                                <td className="px-4 py-3">
                                                                                                        <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-secondary text-foreground/90">
                                                                                                                {element.properties?.element_type ?? "unknown"}
                                                                                                        </span>
                                                                                                </td>
                                                                                                <td className="px-4 py-3 text-foreground/90">
                                                                                                        {element.geometry?.area != null
                                                                                                                ? `${element.geometry.area.toFixed(2)} m²`
                                                                                                                : "—"}
                                                                                                </td>
                                                                                                <td className="px-4 py-3 text-foreground/90">
                                                                                                        v{element.version}
                                                                                                </td>
                                                                                                <td className="px-4 py-3 text-muted-foreground text-xs">
                                                                                                        {element.last_modified_timestamp
                                                                                                                ? new Date(
                                                                                                                                element.last_modified_timestamp,
                                                                                                                        ).toLocaleDateString()
                                                                                                                : "—"}
                                                                                                </td>
                                                                                                <td className="px-4 py-3 text-right">
                                                                                                        <div className="flex items-center justify-end gap-2">
                                                                                                                <Link
                                                                                                                        to={`/elements/${element.element_id}`}
                                                                                                                        className="text-muted-foreground hover:text-white transition-colors px-2 py-1"
                                                                                                                        title="View"
                                                                                                                >
                                                                                                                        <svg
                                                                                                                                width="14"
                                                                                                                                height="14"
                                                                                                                                viewBox="0 0 24 24"
                                                                                                                                fill="none"
                                                                                                                                stroke="currentColor"
                                                                                                                                strokeWidth="2"
                                                                                                                                strokeLinecap="round"
                                                                                                                                strokeLinejoin="round"
                                                                                                                        >
                                                                                                                                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                                                                                                                                <circle cx="12" cy="12" r="3" />
                                                                                                                        </svg>
                                                                                                                </Link>
                                                                                                                <Button
                                                                                                                        variant="ghost"
                                                                                                                        size="icon"
                                                                                                                        onClick={() => setDeleteTarget(element)}
                                                                                                                        className="text-muted-foreground hover:text-danger transition-colors p-0 h-auto"
                                                                                                                        title={t("common.delete")}
                                                                                                                >
                                                                                                                        <svg
                                                                                                                                width="14"
                                                                                                                                height="14"
                                                                                                                                viewBox="0 0 24 24"
                                                                                                                                fill="none"
                                                                                                                                stroke="currentColor"
                                                                                                                                strokeWidth="2"
                                                                                                                                strokeLinecap="round"
                                                                                                                                strokeLinejoin="round"
                                                                                                                        >
                                                                                                                                <polyline points="3 6 5 6 21 6" />
                                                                                                                                <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                                                                                                                        </svg>
                                                                                                                </Button>
                                                                                                        </div>
                                                                                                </td>
                                                                                        </tr>
                                                                                ))
                                                                        )}
                                                                </tbody>
                                                        </table>
                                                </div>
                                        </div>

                                        {/* Pagination */}
                                        {totalPages > 1 && (
                                                <div className="flex items-center justify-between">
                                                        <p className="text-sm text-muted-foreground">
                                                                {t("common.page")} {page} {t("common.of")} {totalPages}
                                                        </p>
                                                        <div className="flex gap-2">
                                                                <button
                                                                        onClick={() => setPage((p) => Math.max(1, p - 1))}
                                                                        disabled={page <= 1}
                                                                        className="px-3 py-1.5 bg-secondary text-white text-sm rounded-lg disabled:opacity-40 hover:bg-slate-600 transition-colors"
                                                                        aria-label={t("common.previous")}
                                                                >
                                                                        {t("common.previous")}
                                                                </button>
                                                                <button
                                                                        onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                                                                        disabled={page >= totalPages}
                                                                        className="px-3 py-1.5 bg-secondary text-white text-sm rounded-lg disabled:opacity-40 hover:bg-slate-600 transition-colors"
                                                                        aria-label={t("common.next")}
                                                                >
                                                                        {t("common.next")}
                                                                </button>
                                                        </div>
                                                </div>
                                        )}
                                </>
                        )}

                        {/* Create Modal */}
                        {showCreateModal && (
                                <CreateElementModal
                                        onClose={() => setShowCreateModal(false)}
                                        onSuccess={() => {
                                                setShowCreateModal(false);
                                                queryClient.invalidateQueries({ queryKey: ["elements"] });
                                        }}
                                />
                        )}

                        {/* Delete Confirmation Modal */}
                        {deleteTarget && (
                                <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
                                        <div className="bg-card border border-border rounded-md max-w-md w-full p-6">
                                                <h3 className="text-lg font-semibold text-white mb-2">
                                                        {t("elements.deleteElement")}
                                                </h3>
                                                <p className="text-muted-foreground text-sm mb-4">
                                                        {t("elements.deleteConfirmation", {
                                                                name: deleteTarget.properties?.name ?? deleteTarget.element_id,
                                                        })}
                                                </p>
                                                {deleteMutation.isError && (
                                                        <p className="text-danger text-sm mb-3">
                                                                {t("elements.deleteFailed")}:{" "}
                                                                {deleteMutation.error instanceof Error
                                                                        ? deleteMutation.error.message
                                                                        : t("common.unknownError")}
                                                        </p>
                                                )}
                                                <div className="flex justify-end gap-3">
                                                        <button
                                                                onClick={() => setDeleteTarget(null)}
                                                                className="px-4 py-2 text-sm text-foreground/90 hover:text-white transition-colors"
                                                        >
                                                                {t("common.cancel")}
                                                        </button>
                                                        <Button
                                                                onClick={() => deleteMutation.mutate(deleteTarget.element_id)}
                                                                disabled={deleteMutation.isPending}
                                                                className="bg-danger hover:bg-danger/90 text-white border-none"
                                                        >
                                                                {deleteMutation.isPending
                                                                        ? t("elements.deleting")
                                                                        : t("common.delete")}
                                                        </Button>
                                                </div>
                                        </div>
                                </div>
                        )}
                </div>
        );
}

// ===== Create Element Modal =====

function CreateElementModal({
        onClose,
        onSuccess,
}: {
        onClose: () => void;
        onSuccess: () => void;
}) {
        const { t } = useTranslation();
        const [name, setName] = useState("");
        const [elementType, setElementType] = useState<string>("wall");
        const [material, setMaterial] = useState("");
        const [fireRating, setFireRating] = useState("");
        const [height, setHeight] = useState("");
        const [width, setWidth] = useState("");
        const [loadBearing, setLoadBearing] = useState(false);
        const [description, setDescription] = useState("");

        const createMutation = useMutation({
                mutationFn: () => {
                        const properties: ElementPropertiesCreate = {
                                element_type: elementType,
                                name,
                                description: description || undefined,
                                material: material || undefined,
                                fire_rating: fireRating || undefined,
                                height: height ? parseFloat(height) : undefined,
                                width: width ? parseFloat(width) : undefined,
                                load_bearing: loadBearing,
                        };

                        // Default geometry with empty points
                        const geometry: ElementGeometryCreate = {
                                points: [],
                                polyline_closed: false,
                        };

                        return api.createElement({ properties, geometry });
                },
                onSuccess,
        });

        return (
                <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
                        <div className="bg-card border border-border rounded-md max-w-lg w-full p-6 max-h-[90vh] overflow-y-auto custom-scrollbar">
                                <h3 className="text-lg font-semibold text-white mb-4">
                                        {t("elements.createElement")}
                                </h3>

                                {createMutation.isError && (
                                        <div className="bg-slate-500/10 border border-slate-500/20 rounded-lg p-3 mb-4">
                                                <p className="text-danger text-sm">
                                                        {createMutation.error instanceof Error
                                                                ? createMutation.error.message
                                                                : t("elements.creationFailed")}
                                                </p>
                                        </div>
                                )}

                                <div className="space-y-4">
                                        <div>
                                                <label className="block text-sm font-medium text-foreground/90 mb-1">
                                                        {t("elements.name")} *
                                                </label>
                                                <Input
                                                        value={name}
                                                        onChange={(e) => setName(e.target.value)}
                                                        className="bg-card border-border text-white"
                                                        placeholder={t("elements.elementNamePlaceholder")}
                                                />
                                        </div>

                                        <div>
                                                <label className="block text-sm font-medium text-foreground/90 mb-1">
                                                        {t("elements.type")} *
                                                </label>
                                                <Select value={elementType} onValueChange={setElementType}>
                                                        <SelectTrigger className="bg-card border-border text-white">
                                                                <SelectValue />
                                                        </SelectTrigger>
                                                        <SelectContent className="bg-card border-border text-white">
                                                                {ELEMENT_TYPES.map((type) => (
                                                                        <SelectItem key={type.value} value={type.value}>
                                                                                {t(type.labelKey)}
                                                                        </SelectItem>
                                                                ))}
                                                        </SelectContent>
                                                </Select>
                                        </div>

                                        <div className="grid grid-cols-2 gap-4">
                                                <div>
                                                        <label className="block text-sm font-medium text-foreground/90 mb-1">
                                                                {t("elements.height")}
                                                        </label>
                                                        <Input
                                                                type="number"
                                                                value={height}
                                                                onChange={(e) => setHeight(e.target.value)}
                                                                className="bg-card border-border text-white"
                                                                placeholder="m"
                                                        />
                                                </div>
                                                <div>
                                                        <label className="block text-sm font-medium text-foreground/90 mb-1">
                                                                {t("elements.width")}
                                                        </label>
                                                        <Input
                                                                type="number"
                                                                value={width}
                                                                onChange={(e) => setWidth(e.target.value)}
                                                                className="bg-card border-border text-white"
                                                                placeholder="m"
                                                        />
                                                </div>
                                        </div>

                                        <div className="grid grid-cols-2 gap-4">
                                                <div>
                                                        <label className="block text-sm font-medium text-foreground/90 mb-1">
                                                                {t("elements.material")}
                                                        </label>
                                                        <Input
                                                                value={material}
                                                                onChange={(e) => setMaterial(e.target.value)}
                                                                className="bg-card border-border text-white"
                                                                placeholder={t("elements.materialPlaceholder")}
                                                        />
                                                </div>
                                                <div>
                                                        <label className="block text-sm font-medium text-foreground/90 mb-1">
                                                                {t("elements.fireRating")}
                                                        </label>
                                                        <Input
                                                                value={fireRating}
                                                                onChange={(e) => setFireRating(e.target.value)}
                                                                className="bg-card border-border text-white"
                                                                placeholder={t("elements.fireRatingPlaceholder")}
                                                        />
                                                </div>
                                        </div>

                                        <div>
                                                <label className="block text-sm font-medium text-foreground/90 mb-1">
                                                        {t("elements.description")}
                                                </label>
                                                <Textarea
                                                        value={description}
                                                        onChange={(e) => setDescription(e.target.value)}
                                                        rows={2}
                                                        className="bg-card border-border text-white resize-none"
                                                        placeholder={t("elements.descriptionPlaceholder")}
                                                />
                                        </div>

                                        <div className="flex items-center gap-2">
                                                <Checkbox
                                                        id="load-bearing"
                                                        checked={loadBearing}
                                                        onCheckedChange={(checked) => setLoadBearing(Boolean(checked))}
                                                        className="data-[state=checked]:bg-danger data-[state=checked]:border-slate-600"
                                                />
                                                <label htmlFor="load-bearing" className="text-sm text-foreground/90">
                                                        {t("elements.loadBearing")}
                                                </label>
                                        </div>
                                </div>

                                <div className="flex justify-end gap-3 mt-6">
                                        <Button
                                                variant="outline"
                                                className="border-border text-foreground/90"
                                                onClick={onClose}
                                        >
                                                {t("common.cancel")}
                                        </Button>
                                        <Button
                                                onClick={() => createMutation.mutate()}
                                                disabled={!name || createMutation.isPending}
                                                className="bg-danger hover:bg-danger/90 text-white border-none"
                                        >
                                                {createMutation.isPending
                                                        ? t("common.creating")
                                                        : t("common.create")}
                                        </Button>
                                </div>
                        </div>
                </div>
        );
}

export default Elements;
