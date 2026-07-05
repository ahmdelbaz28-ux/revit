import type { NextFunction, Request, Response } from "express";

export const errorHandler = (
	err: Error,
	_req: Request,
	res: Response,
	_next: NextFunction,
) => {
	console.error("Error:", err.message);

	// Don't leak internal errors in production
	const isDev = process.env.NODE_ENV === "development";

	res.status(500).json({
		error: "Internal Server Error",
		message: isDev ? err.message : "Something went wrong",
		...(isDev && { stack: err.stack }),
	});
};
