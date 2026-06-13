import { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useTasks, useCreateTask, useUpdateTask, useDeleteTask } from '../hooks/useTasks';
import TaskList from '../components/TaskList';
import TaskModal from '../components/TaskModal';
import TaskFilters from '../components/TaskFilters';
import { toast } from 'sonner';

export default function Dashboard() {
  const { user, logout } = useAuth();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<any>(null);
  const [filters, setFilters] = useState({ status: '', tag: '', dueDate: '' });
  
  const { data, isLoading } = useTasks(filters);
  const createTask = useCreateTask();
  const updateTask = useUpdateTask();
  const deleteTask = useDeleteTask();

  const handleCreate = () => {
    setEditingTask(null);
    setIsModalOpen(true);
  };

  const handleEdit = (task: any) => {
    setEditingTask(task);
    setIsModalOpen(true);
  };

  const handleSave = async (taskData: any) => {
    try {
      if (editingTask) {
        await updateTask.mutateAsync({ id: editingTask.id, ...taskData });
        toast.success('Task updated');
      } else {
        await createTask.mutateAsync(taskData);
        toast.success('Task created');
      }
      setIsModalOpen(false);
    } catch (err: any) {
      toast.error(err.message || 'Failed to save task');
    }
  };

  const handleDelete = async (id: string) => {
    if (confirm('Delete this task?')) {
      try {
        await deleteTask.mutateAsync(id);
        toast.success('Task deleted');
      } catch (err: any) {
        toast.error(err.message || 'Failed to delete');
      }
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-4 flex justify-between items-center">
          <h1 className="text-xl font-bold">My Tasks</h1>
          <div className="flex items-center gap-4">
            <span className="text-sm text-gray-600">{user?.email}</span>
            <button onClick={logout} className="text-sm text-red-600 hover:underline">Logout</button>
          </div>
        </div>
      </header>
      
      <main className="max-w-7xl mx-auto px-4 py-6">
        <div className="flex justify-between items-center mb-6">
          <TaskFilters filters={filters} onChange={setFilters} />
          <button onClick={handleCreate} className="bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700">
            + New Task
          </button>
        </div>
        
        {isLoading ? (
          <p className="text-center py-8">Loading...</p>
        ) : (
          <TaskList tasks={data?.data || []} onEdit={handleEdit} onDelete={handleDelete} />
        )}
      </main>

      <TaskModal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} task={editingTask} onSave={handleSave} />
    </div>
  );
}