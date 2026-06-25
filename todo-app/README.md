# Todo App - Production-Ready Task Manager

A secure, fully-tested To-Do web application with authentication, CRUD operations, and filtering capabilities.

## Tech Stack

**Backend:**
- Node.js + Express
- PostgreSQL via Prisma ORM
- JWT authentication
- Zod validation
- Jest + Supertest for testing

**Frontend:**
- React 18 + TypeScript
- Tailwind CSS
- React Query (TanStack Query)
- React Hook Form + Zod
- Vitest + React Testing Library

**Infrastructure:**
- GitHub Actions CI/CD
- Vercel (frontend deployment ready)
- Railway/Render (backend deployment ready)

## Features

✅ User authentication (signup/login with JWT)  
✅ Create, read, update, delete tasks  
✅ Filter by status (pending, in progress, completed)  
✅ Filter by tag  
✅ Filter by due date (today, this week, overdue)  
✅ Pagination  
✅ Input validation with Zod  
✅ OWASP Top 10 security hardening  
✅ 80%+ test coverage  
✅ RESTful API design  

## Getting Started

### Prerequisites

- Node.js 20+
- PostgreSQL 15+

### Backend Setup

```bash
cd apps/api
cp .env.example .env
# Edit .env with your DATABASE_URL and JWT_SECRET
npm install
npx prisma migrate dev
npm run dev
```

### Frontend Setup

```bash
cd apps/web
npm install
npm run dev
```

### Run Tests

```bash
# All tests
npm test

# Backend only
npm run test:api

# Frontend only  
npm run test:web
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /auth/signup | Create new user |
| POST | /auth/login | Login user |
| GET | /tasks | List tasks (paginated, filterable) |
| GET | /tasks/:id | Get single task |
| POST | /tasks | Create task |
| PATCH | /tasks/:id | Update task |
| DELETE | /tasks/:id | Delete task |

## Environment Variables

```env
DATABASE_URL=postgresql://user:password@localhost:5432/todoapp
JWT_SECRET=your-super-secret-key
JWT_EXPIRES_IN=7d
PORT=3001
NODE_ENV=development
CORS_ORIGIN=http://localhost:5173
```

## Security Features

- Helmet.js for HTTP headers
- Rate limiting (100 requests/15 min)
- bcrypt password hashing (cost factor 12)
- JWT with expiration
- Parameterized queries (Prisma)
- Input validation (Zod)
- Strict CORS
- Error messages don't leak internals

## License

MIT