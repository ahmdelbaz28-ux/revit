interface Props {
  filters: { status: string; tag: string; dueDate: string };
  onChange: (filters: any) => void;
}

export default function TaskFilters({ filters, onChange }: Props) {
  return (
    <div className="flex gap-3 flex-wrap">
      <select
        value={filters.status}
        onChange={(e) => onChange({ ...filters, status: e.target.value })}
        className="border rounded-lg px-3 py-2"
      >
        <option value="">All Status</option>
        <option value="PENDING">Pending</option>
        <option value="IN_PROGRESS">In Progress</option>
        <option value="COMPLETED">Completed</option>
      </select>
      <select
        value={filters.dueDate}
        onChange={(e) => onChange({ ...filters, dueDate: e.target.value })}
        className="border rounded-lg px-3 py-2"
      >
        <option value="">All Dates</option>
        <option value="today">Today</option>
        <option value="week">This Week</option>
        <option value="overdue">Overdue</option>
      </select>
      <input
        type="text"
        placeholder="Filter by tag..."
        value={filters.tag}
        onChange={(e) => onChange({ ...filters, tag: e.target.value })}
        className="border rounded-lg px-3 py-2"
      />
    </div>
  );
}