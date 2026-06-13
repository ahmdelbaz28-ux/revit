import request from 'supertest';
import { app } from '../index';
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

describe('Auth API', () => {
  beforeAll(async () => {
    // Clean up test data
    await prisma.taskTag.deleteMany();
    await prisma.task.deleteMany();
    await prisma.tag.deleteMany();
    await prisma.user.deleteMany({
      where: { email: 'test@example.com' }
    });
  });

  afterAll(async () => {
    await prisma.$disconnect();
  });

  describe('POST /auth/signup', () => {
    it('should create a new user and return token', async () => {
      const res = await request(app)
        .post('/auth/signup')
        .send({
          email: 'test@example.com',
          password: 'password123',
          name: 'Test User'
        });
      
      expect(res.status).toBe(201);
      expect(res.body).toHaveProperty('user');
      expect(res.body).toHaveProperty('token');
      expect(res.body.user.email).toBe('test@example.com');
      expect(res.body.token).toBeTruthy();
    });

    it('should return 409 if email already exists', async () => {
      const res = await request(app)
        .post('/auth/signup')
        .send({
          email: 'test@example.com',
          password: 'password123'
        });
      
      expect(res.status).toBe(409);
      expect(res.body.error).toBe('Conflict');
    });

    it('should return 422 for invalid email', async () => {
      const res = await request(app)
        .post('/auth/signup')
        .send({
          email: 'invalid-email',
          password: 'password123'
        });
      
      expect(res.status).toBe(422);
      expect(res.body.error).toBe('Validation Error');
    });

    it('should return 422 for short password', async () => {
      const res = await request(app)
        .post('/auth/signup')
        .send({
          email: 'new@example.com',
          password: 'short'
        });
      
      expect(res.status).toBe(422);
      expect(res.body.error).toBe('Validation Error');
    });

    it('should return 422 when email is missing', async () => {
      const res = await request(app)
        .post('/auth/signup')
        .send({
          password: 'password123'
        });
      
      expect(res.status).toBe(422);
    });
  });

  describe('POST /auth/login', () => {
    it('should login with valid credentials', async () => {
      const res = await request(app)
        .post('/auth/login')
        .send({
          email: 'test@example.com',
          password: 'password123'
        });
      
      expect(res.status).toBe(200);
      expect(res.body).toHaveProperty('user');
      expect(res.body).toHaveProperty('token');
    });

    it('should return 401 for invalid password', async () => {
      const res = await request(app)
        .post('/auth/login')
        .send({
          email: 'test@example.com',
          password: 'wrongpassword'
        });
      
      expect(res.status).toBe(401);
      expect(res.body.error).toBe('Unauthorized');
    });

    it('should return 401 for non-existent user', async () => {
      const res = await request(app)
        .post('/auth/login')
        .send({
          email: 'nonexistent@example.com',
          password: 'password123'
        });
      
      expect(res.status).toBe(401);
    });

    it('should return 422 for missing credentials', async () => {
      const res = await request(app)
        .post('/auth/login')
        .send({});
      
      expect(res.status).toBe(422);
    });
  });
});
