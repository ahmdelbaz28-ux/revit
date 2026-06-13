import { format } from 'date-fns';

interface Task {
  id: string;
  title: string;
  notes?: string;
  status: string;
  dueDate?: string;
  tags: { id: string; name: string; color: string }[];
}

interface Props {
  tasks: Task[];
  onEdit: (task: Task) => void;
  onDelete: (id: string) => void;
}

export default function TaskList({ tasks, onEdit, onDelete }: Props) {
  if (tasks.length === 0) {
    return <p className="text-center py-8 text-gray-500">No tasks yet. Create one!</p>;
  }

  return (
    <div className="space-y-3">
      {tasks.map((task) => (
        <div key={task.id} className="bg-white p-4 rounded-lg shadow-sm border hover:shadow-md transition">
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <h3 className="font-medium">{task.title}</h3>
              {task.notes && <p className="text-sm text-gray-500 mt-1">{task.notes}</p>}
              <div className="flex gap-2 mt-2 flex-wrap">
                {task.tags.map((tag) => (
                  <span key={tag.id} className="px-2 py-0.5 text-xs rounded-full" style={{ backgroundColor: tag.color + '20', color: tag.color }}>
                    {tag.name}
                  </span>
                ))}
                {task.dueDate && (
                  <span className="text-xs text-gray-400">
                    Due: {format(new Date(task.dueDate), 'MMM d, yyyy')}
                  </span>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2 ml-4">
              <select
                value={task.status}
                onChange={(e) => onEdit({ ...task, status: e.target.value })}
                className="text-sm border rounded px-2 py-1"
              >
                <option value="PENDING">Pending</option>
                <option value="IN_PROGRESS">In Progress</option>
                <option value="COMPLETED">Completed</option>
              </select>
              <button onClick={() => onEdit(task)} className="text-primary-600 hover:underline text-sm">Edit</button>
              <button onClick={() => onDelete(task.id)} className="text-red-600 hover:underline text-sm">Delete</button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}