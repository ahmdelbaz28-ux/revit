import { Router, Request, Response } from 'express';
import { z } from 'zod';
import { prisma } from '../index';
import { requireAuth } from '../middleware/auth';
import { errorHandler } from '../middleware/errorHandler';

const router = Router();

// Validation schemas
const createTaskSchema = z.object({
  title: z.string().min(1, 'Title is required').max(200),
  notes: z.string().max(2000).optional(),
  dueDate: z.string().datetime().optional().nullable(),
  status: z.enum(['PENDING', 'IN_PROGRESS', 'COMPLETED']).optional(),
  tags: z.array(z.string()).optional()
});

const updateTaskSchema = z.object({
  title: z.string().min(1).max(200).optional(),
  notes: z.string().max(2000).optional().nullable(),
  dueDate: z.string().datetime().optional().nullable(),
  status: z.enum(['PENDING', 'IN_PROGRESS', 'COMPLETED']).optional(),
  tags: z.array(z.string()).optional()
});

const querySchema = z.object({
  page: z.string().regex(/\d+/).optional().transform(v => parseInt(v || '1')),
  limit: z.string().regex(/\d+/).optional().transform(v => Math.min(parseInt(v || '10'), 100)),
  status: z.enum(['PENDING', 'IN_PROGRESS', 'COMPLETED']).optional(),
  tag: z.string().optional(),
  dueDate: z.enum(['today', 'week', 'overdue']).optional()
});

// Apply auth middleware to all task routes
router.use(requireAuth);

// GET /tasks
export const getTasks = async (req: Request, res: Response) => {
  try {
    const { page, limit, status, tag, dueDate } = querySchema.parse(req.query);
    const skip = (page - 1) * limit;
    
    // Build where clause
    const where: any = { userId: (req as any).user.userId };
    
    if (status) where.status = status;
    if (tag) where.taskTags = { some: { tag: { name: tag } } };
    
    if (dueDate === 'today') {
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      const tomorrow = new Date(today);
      tomorrow.setDate(tomorrow.getDate() + 1);
      where.dueDate = { gte: today, lt: tomorrow };
    } else if (dueDate === 'week') {
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      const weekEnd = new Date(today);
      weekEnd.setDate(weekEnd.getDate() + 7);
      where.dueDate = { gte: today, lte: weekEnd };
    } else if (dueDate === 'overdue') {
      where.dueDate = { lt: new Date(), status: { not: 'COMPLETED' } };
    }
    
    const [tasks, total] = await Promise.all([
      prisma.task.findMany({
        where,
        skip,
        take: limit,
        orderBy: { createdAt: 'desc' },
        include: { taskTags: { include: { tag: true } } }
      }),
      prisma.task.count({ where })
    ]);
    
    res.json({
      data: tasks.map((t: any) => ({ ...t, tags: t.taskTags.map((tt: any) => tt.tag) })),
      pagination: {
        page,
        limit,
        total,
        totalPages: Math.ceil(total / limit)
      }
    });
  } catch (error) {
    if (error instanceof z.ZodError) {
      return res.status(422).json({ error: 'Validation Error', details: error.errors });
    }
    errorHandler(error as Error, req, res, () => {});
  }
};

// GET /tasks/:id
export const getTaskById = async (req: Request, res: Response) => {
  try {
    const { id } = req.params;
    const userId = (req as any).user.userId;
    
    const task = await prisma.task.findFirst({
      where: { id, userId },
      include: { taskTags: { include: { tag: true } } }
    });
    
    if (!task) {
      return res.status(404).json({ error: 'Not Found', message: 'Task not found' });
    }
    
    res.json({ ...task, tags: task.taskTags.map((tt: any) => tt.tag) });
  } catch (error) {
    errorHandler(error as Error, req, res, () => {});
  }
};

// POST /tasks
export const createTask = async (req: Request, res: Response) => {
  try {
    const data = createTaskSchema.parse(req.body);
    const userId = (req as any).user.userId;
    
    // Handle tags
    let tagConnections: { id: string }[] = [];
    if (data.tags && data.tags.length > 0) {
      // Upsert tags and get their IDs
      const tagIds = await Promise.all(
        data.tags.map(async (tagName) => {
          const tag = await prisma.tag.upsert({
            where: { name: tagName },
            update: {},
            create: { name: tagName }
          });
          return tag.id;
        })
      );
      tagConnections = tagIds.map(id => ({ id }));
    }
    
    const task = await prisma.task.create({
      data: {
        title: data.title,
        notes: data.notes,
        dueDate: data.dueDate ? new Date(data.dueDate) : null,
        status: data.status || 'PENDING',
        userId,
        taskTags: tagConnections.length > 0 ? { create: tagConnections.map(id => ({ tagId: id.id })) } : undefined
      },
      include: { taskTags: { include: { tag: true } } }
    });
    
    res.status(201).json({ ...task, tags: task.taskTags.map((tt: any) => tt.tag) });
  } catch (error) {
    if (error instanceof z.ZodError) {
      return res.status(422).json({ error: 'Validation Error', details: error.errors });
    }
    errorHandler(error as Error, req, res, () => {});
  }
};

// PATCH /tasks/:id
export const updateTask = async (req: Request, res: Response) => {
  try {
    const { id } = req.params;
    const data = updateTaskSchema.parse(req.body);
    const userId = (req as any).user.userId;
    
    // Check ownership
    const existing = await prisma.task.findFirst({ where: { id, userId } });
    if (!existing) {
      return res.status(404).json({ error: 'Not Found', message: 'Task not found' });
    }
    
    // Handle tags update
    if (data.tags !== undefined) {
      // Delete existing taskTags
      await prisma.taskTag.deleteMany({ where: { taskId: id } });
      
      // Create new ones
      if (data.tags.length > 0) {
        const tagIds = await Promise.all(
          data.tags.map(async (tagName) => {
            const tag = await prisma.tag.upsert({
              where: { name: tagName },
              update: {},
              create: { name: tagName }
            });
            return tag.id;
          })
        );
        await prisma.taskTag.createMany({
          data: tagIds.map(tagId => ({ taskId: id, tagId }))
        });
      }
    }
    
    const task = await prisma.task.update({
      where: { id },
      data: {
        title: data.title,
        notes: data.notes,
        dueDate: data.dueDate ? new Date(data.dueDate) : data.dueDate === null ? null : undefined,
        status: data.status
      },
      include: { taskTags: { include: { tag: true } } }
    });
    
    res.json({ ...task, tags: task.taskTags.map((tt: any) => tt.tag) });
  } catch (error) {
    if (error instanceof z.ZodError) {
      return res.status(422).json({ error: 'Validation Error', details: error.errors });
    }
    errorHandler(error as Error, req, res, () => {});
  }
};

// DELETE /tasks/:id
export const deleteTask = async (req: Request, res: Response) => {
  try {
    const { id } = req.params;
    const userId = (req as any).user.userId;
    
    const task = await prisma.task.findFirst({ where: { id, userId } });
    if (!task) {
      return res.status(404).json({ error: 'Not Found', message: 'Task not found' });
    }
    
    await prisma.task.delete({ where: { id } });
    
    res.status(204).send();
  } catch (error) {
    errorHandler(error as Error, req, res, () => {});
  }
};

router.get('/', getTasks);
router.get('/:id', getTaskById);
router.post('/', createTask);
router.patch('/:id', updateTask);
router.delete('/:id', deleteTask);

export { router as tasksRouter };
