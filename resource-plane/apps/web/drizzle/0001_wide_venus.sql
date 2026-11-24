ALTER TABLE "projects" ADD COLUMN "region" text DEFAULT 'us-east-1' NOT NULL;--> statement-breakpoint
ALTER TABLE "projects" ADD COLUMN "updated_at" timestamp DEFAULT now() NOT NULL;