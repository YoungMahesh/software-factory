import {
	pgTable,
	text,
	timestamp,
	integer,
	uuid,
	serial,
} from "drizzle-orm/pg-core";

export const projects = pgTable("projects", {
	id: uuid("id").defaultRandom().primaryKey(),
	name: text("name").notNull(),
	slug: text("slug").notNull().unique(),
	region: text("region").notNull().default("us-east-1"),
	createdAt: timestamp("created_at").defaultNow().notNull(),
	updatedAt: timestamp("updated_at").defaultNow().notNull(),
});

export const databases = pgTable("databases", {
	id: uuid("id").defaultRandom().primaryKey(),
	projectId: uuid("project_id")
		.notNull()
		.references(() => projects.id, { onDelete: "cascade" }),
	name: text("name").notNull(),
	username: text("username").notNull(),
	password: text("password").notNull(),
	host: text("host").notNull().default("localhost"),
	port: integer("port").notNull().default(5432),
	createdAt: timestamp("created_at").defaultNow().notNull(),
});

export const objectStorages = pgTable("object_storages", {
	id: uuid("id").defaultRandom().primaryKey(),
	projectId: uuid("project_id")
		.notNull()
		.references(() => projects.id, { onDelete: "cascade" }),
	bucketName: text("bucket_name").notNull(),
	accessKeyId: text("access_key_id").notNull(),
	secretAccessKey: text("secret_access_key").notNull(),
	endpoint: text("endpoint").notNull().default("http://localhost:8333"),
	region: text("region").notNull().default("us-east-1"),
	createdAt: timestamp("created_at").defaultNow().notNull(),
});

export const settings = pgTable("settings", {
	key: text("key").primaryKey(),
	value: text("value").notNull(),
});

export const todos = pgTable("todos", {
	id: serial("id").primaryKey(),
	title: text("title").notNull(),
	createdAt: timestamp("created_at").defaultNow(),
});
