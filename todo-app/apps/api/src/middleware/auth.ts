// NOSONAR
import type { NextFunction, Request, Response } from "express";
import jwt from "jsonwebtoken";

export interface AuthRequest extends Request {
	user?: { userId: string; email: string };
}

/**
 * Get JWT secret from environment variable.
 * CRITICAL: Fails loudly if JWT_SECRET is not set in production.
 * Using a hardcoded secret allows attackers to forge tokens.
 */
function getJwtSecret(): string {
	const secret = process.env.JWT_SECRET;
	if (!secret) {
		if (process.env.NODE_ENV === "production") {
			throw new Error(
				"FATAL: JWT_SECRET environment variable is not set. " +
					"Refusing to authenticate requests with no secret configured. " +
					"Set JWT_SECRET before starting the server.",
			);
		}
		// In development only, use a clearly invalid default that logs a warning
		console.warn(
			"[SECURITY WARNING] JWT_SECRET is not set! Using insecure development default. " +
				"This MUST be set in production.",
		);
		return "dev-only-insecure-secret-DO-NOT-USE-IN-PRODUCTION";
	}
	return secret;
}

export const requireAuth = (
	req: AuthRequest,
	res: Response,
	next: NextFunction,
) => {
	try {
		const authHeader = req.headers.authorization;

		if (!authHeader?.startsWith("Bearer ")) {
			return res.status(401).json({
				error: "Unauthorized",
				message: "No token provided",
			});
		}

		const token = authHeader.split(" ")[1];

		const decoded = jwt.verify(token, getJwtSecret()) as {
			userId: string;
			email: string;
		};

		req.user = decoded;
		next();
	} catch (error) {
		if (error instanceof jwt.TokenExpiredError) {
			return res.status(401).json({
				error: "Unauthorized",
				message: "Token expired",
			});
		}
		if (error instanceof jwt.JsonWebTokenError) {
			return res.status(401).json({
				error: "Unauthorized",
				message: "Invalid token",
			});
		}
		return res.status(401).json({
			error: "Unauthorized",
			message: "Authentication failed",
		});
	}
};
