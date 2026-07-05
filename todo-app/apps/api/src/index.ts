import { PrismaClient } from "@prisma/client";
import cors from "cors";
import { config } from "dotenv";
import express from "express";
import rateLimit from "express-rate-limit";
import helmet from "helmet";
import { errorHandler } from "./middleware/errorHandler";
import { authRouter } from "./routes/auth";
import { tasksRouter } from "./routes/tasks";

config();

const app = express();
const prisma = new PrismaClient();

// Security middleware
app.use(helmet());
app.use(
	cors({
		origin: (() => {
			const origin = process.env.CORS_ORIGIN;
			if (!origin) {
				if (process.env.NODE_ENV === "production") {
					// In production, CORS_ORIGIN MUST be explicitly set
					console.error(
						"[SECURITY] CORS_ORIGIN environment variable is not set. " +
							"No origins will be allowed. Set CORS_ORIGIN to your frontend URL.",
					);
					return ""; // No origins allowed if not configured
				}
				// Development only
				console.warn(
					"[SECURITY] CORS_ORIGIN not set, using development default. " +
						"This MUST be set in production.",
				);
				return "http://localhost:5173";
			}
			// Support multiple origins separated by comma
			return origin.split(",").map((o) => o.trim());
		})(),
		credentials: true,
	}),
);

// Rate limiting
const limiter = rateLimit({
	windowMs: 15 * 60 * 1000, // 15 minutes
	max: 100, // limit each IP to 100 requests per windowMs
});
app.use(limiter);

// Body parsing
app.use(express.json({ limit: "10kb" }));

// Health check
app.get("/health", (_req, res) => {
	res.json({ status: "ok", timestamp: new Date().toISOString() });
});

// Routes
app.use("/auth", authRouter);
app.use("/tasks", tasksRouter);

// Error handling
// Handle JSON parsing errors specifically
app.use(
	(
		err: any,
		req: express.Request,
		res: express.Response,
		next: express.NextFunction,
	) => {
		if (err.type === "entity.parse.failed") {
			return res
				.status(400)
				.json({ error: "Bad Request", message: "Invalid JSON" });
		}
		errorHandler(err, req, res, next);
	},
);
app.use(errorHandler);

// Start server (skip in test environment)
const PORT = process.env.PORT || 3001;
if (process.env.NODE_ENV !== "test") {
	app.listen(PORT, () => {
		console.log(`API server running on port ${PORT}`);
	});
}

// Graceful shutdown
process.on("SIGTERM", async () => {
	await prisma.$disconnect();
	process.exit(0);
});

export { app, prisma };
