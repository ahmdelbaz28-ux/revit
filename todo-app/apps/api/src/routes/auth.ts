import { Router, Request, Response } from 'express';
import bcrypt from 'bcrypt';
import jwt from 'jsonwebtoken';
import { z } from 'zod';
import { prisma } from '../index';
import { errorHandler } from '../middleware/errorHandler';

const router = Router();

const signupSchema = z.object({
  email: z.string().email('Invalid email format'),
  password: z.string().min(8, 'Password must be at least 8 characters'),
  name: z.string().min(1).optional()
});

const loginSchema = z.object({
  email: z.string().email('Invalid email format'),
  password: z.string().min(1, 'Password is required')
});

// POST /auth/signup
export const signup = async (req: Request, res: Response) => {
  try {
    const { email, password, name } = signupSchema.parse(req.body);
    
    // Check if user exists
    const existingUser = await prisma.user.findUnique({ where: { email } });
    if (existingUser) {
      return res.status(409).json({ 
        error: 'Conflict',
        message: 'User with this email already exists'
      });
    }
    
    // Hash password
    const hashedPassword = await bcrypt.hash(password, 12);
    
    // Create user
    const user = await prisma.user.create({
      data: { email, password: hashedPassword, name },
      select: { id: true, email: true, name: true, createdAt: true }
    });
    
    // Generate JWT
    const token = jwt.sign(
      { userId: user.id, email: user.email },
      process.env.JWT_SECRET || 'default-secret',
      { expiresIn: process.env.JWT_EXPIRES_IN || '7d' } as any
    );
    
    res.status(201).json({ user, token });
  } catch (error) {
    if (error instanceof z.ZodError) {
      return res.status(422).json({ 
        error: 'Validation Error',
        details: error.errors 
      });
    }
    errorHandler(error as Error, req, res, () => {});
  }
};

// POST /auth/login
export const login = async (req: Request, res: Response) => {
  try {
    const { email, password } = loginSchema.parse(req.body);
    
    // Find user
    const user = await prisma.user.findUnique({ where: { email } });
    if (!user) {
      return res.status(401).json({ 
        error: 'Unauthorized',
        message: 'Invalid email or password'
      });
    }
    
    // Verify password
    const isValid = await bcrypt.compare(password, user.password);
    if (!isValid) {
      return res.status(401).json({ 
        error: 'Unauthorized',
        message: 'Invalid email or password'
      });
    }
    
    // Generate JWT
    const token = jwt.sign(
      { userId: user.id, email: user.email },
      process.env.JWT_SECRET || 'default-secret',
      { expiresIn: process.env.JWT_EXPIRES_IN || '7d' } as any
    );
    
    res.json({ 
      user: { id: user.id, email: user.email, name: user.name },
      token 
    });
  } catch (error) {
    if (error instanceof z.ZodError) {
      return res.status(422).json({ 
        error: 'Validation Error',
        details: error.errors 
      });
    }
    errorHandler(error as Error, req, res, () => {});
  }
};

router.post('/signup', signup);
router.post('/login', login);

export { router as authRouter };
