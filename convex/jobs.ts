import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

const SEGMENT = v.object({
  start: v.string(),
  end: v.string(),
  title: v.string(),
});

export const createJob = mutation({
  args: {
    sourceUrl: v.string(),
  },
  handler: async (ctx: any, args: any) => {
    const now = Date.now();
    return await ctx.db.insert("jobs", {
      sourceUrl: args.sourceUrl,
      status: "queued",
      createdAt: now,
      updatedAt: now,
      nextSegmentIndex: 0,
      uploadedCount: 0,
    });
  },
});

export const listJobs = query({
  args: {},
  handler: async (ctx: any) => {
    return await ctx.db.query("jobs").order("desc").collect();
  },
});

export const claimNextJob = mutation({
  args: {},
  handler: async (ctx: any) => {
    const now = Date.now();
    const jobs = await ctx.db.query("jobs").order("asc").collect();
    const job = jobs.find((entry: any) => {
      if (entry.status === "queued") return true;
      if (entry.status === "waiting_retry") {
        return !entry.retryAt || entry.retryAt <= now;
      }
      return false;
    });

    if (!job) {
      return null;
    }

    await ctx.db.patch(job._id, {
      status: "processing",
      lastAttemptAt: now,
      updatedAt: now,
    });

    return await ctx.db.get(job._id);
  },
});

export const markProcessing = mutation({
  args: {
    id: v.id("jobs"),
  },
  handler: async (ctx: any, args: any) => {
    const now = Date.now();
    await ctx.db.patch(args.id, {
      status: "processing",
      updatedAt: now,
      lastAttemptAt: now,
    });
  },
});

export const setAnalysis = mutation({
  args: {
    id: v.id("jobs"),
    videoId: v.string(),
    videoTitle: v.string(),
    segments: v.array(SEGMENT),
    totalSegments: v.number(),
  },
  handler: async (ctx: any, args: any) => {
    await ctx.db.patch(args.id, {
      videoId: args.videoId,
      videoTitle: args.videoTitle,
      segments: args.segments,
      totalSegments: args.totalSegments,
      status: "processing",
      updatedAt: Date.now(),
    });
  },
});

export const setProgress = mutation({
  args: {
    id: v.id("jobs"),
    nextSegmentIndex: v.number(),
    uploadedCount: v.number(),
    lastError: v.optional(v.string()),
  },
  handler: async (ctx: any, args: any) => {
    const patch: Record<string, unknown> = {
      nextSegmentIndex: args.nextSegmentIndex,
      uploadedCount: args.uploadedCount,
      updatedAt: Date.now(),
    };

    if (args.lastError !== undefined) {
      patch.lastError = args.lastError;
    }

    await ctx.db.patch(args.id, patch);
  },
});

export const markRetry = mutation({
  args: {
    id: v.id("jobs"),
    nextSegmentIndex: v.number(),
    retryAt: v.number(),
    lastError: v.string(),
  },
  handler: async (ctx: any, args: any) => {
    await ctx.db.patch(args.id, {
      status: "waiting_retry",
      nextSegmentIndex: args.nextSegmentIndex,
      retryAt: args.retryAt,
      lastError: args.lastError,
      updatedAt: Date.now(),
    });
  },
});

export const markFailure = mutation({
  args: {
    id: v.id("jobs"),
    lastError: v.string(),
  },
  handler: async (ctx: any, args: any) => {
    await ctx.db.patch(args.id, {
      status: "failed",
      lastError: args.lastError,
      updatedAt: Date.now(),
    });
  },
});

export const markComplete = mutation({
  args: {
    id: v.id("jobs"),
  },
  handler: async (ctx: any, args: any) => {
    await ctx.db.patch(args.id, {
      status: "completed",
      updatedAt: Date.now(),
    });
  },
});
