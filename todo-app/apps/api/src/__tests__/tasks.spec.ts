import request from 'supertest';
import { app } from '../index';
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

describe('Tasks API', () => {
  let authToken: string;
  let userId: string;

  beforeAll(async () => {
    // Create test user
    const res = await request(app)
      .post('/auth/signup')
      .send({
        email: 'tasks@example.com',
        password: 'password123',
        name: 'Tasks User'
      });
    
    authToken = res.body.token;
    userId = res.body.user.id;
  });

  afterAll(async () => {
    await prisma.taskTag.deleteMany();
    await prisma.task.deleteMany({ where: { userId } });
    await prisma.tag.deleteMany();
    await prisma.user.delete({ where: { email: 'tasks@example.com' } });
    await prisma.$disconnect();
  });

  describe('GET /tasks', () => {
    it('should return empty list for new user', async () => {
      const res = await request(app)
        .get('/tasks')
        .set('Authorization', `Bearer ${authToken}`);
      
      expect(res.status).toBe(200);
      expect(res.body.data).toEqual([]);
      expect(res.body.pagination).toBeDefined();
    });

    it('should return 401 without token', async () => {
      const res = await request(app).get('/tasks');
      
      expect(res.status).toBe(401);
    });

    it('should return 401 with invalid token', async () => {
      const res = await request(app)
        .get('/tasks')
        .set('Authorization', 'Bearer invalid-token');
      
      expect(res.status).toBe(401);
    });

    it('should support pagination', async () => {
      const res = await request(app)
        .get('/tasks?page=1&limit=5')
        .set('Authorization', `Bearer ${authToken}`);
      
      expect(res.status).toBe(200);
      expect(res.body.pagination.page).toBe(1);
      expect(res.body.pagination.limit).toBe(5);
    });

    it('should filter by status', async () => {
      // Create a task
      await request(app)
        .post('/tasks')
        .set('Authorization', `Bearer ${authToken}`)
        .send({ title: 'Test Task', status: 'COMPLETED' });
      
      const res = await request(app)
        .get('/tasks?status=COMPLETED')
        .set('Authorization', `Bearer ${authToken}`);
      
      expect(res.status).toBe(200);
      expect(res.body.data.length).toBeGreaterThan(0);
    });
  });

  describe('POST /tasks', () => {
    it('should create a task', async () => {
      const res = await request(app)
        .post('/tasks')
        .set('Authorization', `Bearer ${authToken}`)
        .send({
          title: 'My First Task',
          notes: 'Some notes',
          status: 'PENDING'
        });
      
      expect(res.status).toBe(201);
      expect(res.body.title).toBe('My First Task');
      expect(res.body.notes).toBe('Some notes');
      expect(res.body.status).toBe('PENDING');
    });

    it('should create task with tags', async () => {
      const res = await request(app)
        .post('/tasks')
        .set('Authorization', `Bearer ${authToken}`)
        .send({
          title: 'Task with Tags',
          tags: ['urgent', 'work']
        });
      
      expect(res.status).toBe(201);
      expect(res.body.tags).toBeDefined();
      expect(res.body.tags.length).toBe(2);
    });

    it('should create task with due date', async () => {
      const dueDate = new Date(Date.now() + 86400000).toISOString();
      const res = await request(app)
        .post('/tasks')
        .set('Authorization', `Bearer ${authToken}`)
        .send({
          title: 'Task with Due Date',
          dueDate
        });
      
      expect(res.status).toBe(201);
      expect(res.body.dueDate).toBeDefined();
    });

    it('should return 422 for missing title', async () => {
      const res = await request(app)
        .post('/tasks')
        .set('Authorization', `Bearer ${authToken}`)
        .send({ notes: 'No title' });
      
      expect(res.status).toBe(422);
    });

    it('should return 422 for empty title', async () => {
      const res = await request(app)
        .post('/tasks')
        .set('Authorization', `Bearer ${authToken}`)
        .send({ title: '' });
      
      expect(res.status).toBe(422);
    });
  });

  describe('PATCH /tasks/:id', () => {
    let taskId: string;

    beforeAll(async () => {
      const res = await request(app)
        .post('/tasks')
        .set('Authorization', `Bearer ${authToken}`)
        .send({ title: 'Task to Update' });
      taskId = res.body.id;
    });

    it('should update task title', async () => {
      const res = await request(app)
        .patch(`/tasks/${taskId}`)
        .set('Authorization', `Bearer ${authToken}`)
        .send({ title: 'Updated Title' });
      
      expect(res.status).toBe(200);
      expect(res.body.title).toBe('Updated Title');
    });

    it('should update task status', async () => {
      const res = await request(app)
        .patch(`/tasks/${taskId}`)
        .set('Authorization', `Bearer ${authToken}`)
        .send({ status: 'COMPLETED' });
      
      expect(res.status).toBe(200);
      expect(res.body.status).toBe('COMPLETED');
    });

    it('should return 404 for non-existent task', async () => {
      const res = await request(app)
        .patch('/tasks/non-existent-id')
        .set('Authorization', `Bearer ${authToken}`)
        .send({ title: 'Hacked' });
      
      expect(res.status).toBe(404);
    });

    it('should return 422 for invalid status', async () => {
      const res = await request(app)
        .patch(`/tasks/${taskId}`)
        .set('Authorization', `Bearer ${authToken}`)
        .send({ status: 'INVALID' });
      
      expect(res.status).toBe(422);
    });
  });

  describe('DELETE /tasks/:id', () => {
    let taskId: string;

    beforeAll(async () => {
      const res = await request(app)
        .post('/tasks')
        .set('Authorization', `Bearer ${authToken}`)
        .send({ title: 'Task to Delete' });
      taskId = res.body.id;
    });

    it('should delete task', async () => {
      const res = await request(app)
        .delete(`/tasks/${taskId}`)
        .set('Authorization', `Bearer ${authToken}`);
      
      expect(res.status).toBe(204);
    });

    it('should return 404 for deleted task', async () => {
      const res = await request(app)
        .get(`/tasks/${taskId}`)
        .set('Authorization', `Bearer ${authToken}`);
      
      expect(res.status).toBe(404);
    });
  });

  // Edge cases
  describe('Edge Cases', () => {
    it('should handle huge payload gracefully', async () => {
      const hugeTitle = 'a'.repeat(10000);
      const res = await request(app)
        .post('/tasks')
        .set('Authorization', `Bearer ${authToken}`)
        .send({ title: hugeTitle });
      
      expect(res.status).toBe(422);
    });

    it('should handle malformed JSON', async () => {
      const res = await request(app)
        .post('/tasks')
        .set('Authorization', `Bearer ${authToken}`)
        .set('Content-Type', 'application/json')
        .send('{ invalid json }');
      
      expect(res.status).toBe(400);
    });

    it('should not allow access to other users tasks', async () => {
      // Create another user
      const res2 = await request(app)
        .post('/auth/signup')
        .send({
          email: 'other@example.com',
          password: 'password123'
        });
      
      const otherToken = res2.body.token;
      
      // Create task as first user
      const taskRes = await request(app)
        .post('/tasks')
        .set('Authorization', `Bearer ${authToken}`)
        .send({ title: 'Private Task' });
      
      // Try to access as other user
      const res = await request(app)
        .get(`/tasks/${taskRes.body.id}`)
        .set('Authorization', `Bearer ${otherToken}`);
      
      expect(res.status).toBe(404);
      
      // Cleanup
      await prisma.user.delete({ where: { email: 'other@example.com' } });
    });
  });
});
