"use server";

import {
  createProject,
  listProjects,
  getProject,
} from "@/services/projects";
import {
  createDatabase,
  deleteDatabase,
  listDatabases,
  resetDatabasePassword,
  getDatabaseCredentials,
} from "@/services/databases";
import {
  createObjectStorage,
  deleteObjectStorage,
  listObjectStorages,
  getStorageCredentials,
} from "@/services/storage";
import { executeSqlQuery, type SqlExecutionResult } from "@/services/scratchpad";
import {
  listBucketObjects,
  uploadBucketObject,
  deleteBucketObject,
  getObjectContent,
  type BucketObject,
  type DownloadObjectResult,
} from "@/services/browser";

export async function createProjectFn(opts: { data: { name: string; slug?: string; region?: string } } | { name: string; slug?: string; region?: string }) {
  const data = "data" in opts ? opts.data : opts;
  return createProject(data);
}

export async function createDatabaseFn(opts: { data: { projectId: string; name: string } }) {
  return createDatabase(opts.data);
}

export async function listDatabasesFn(opts: { data: { projectId: string } } | string) {
  const projectId = typeof opts === "string" ? opts : opts.data.projectId;
  return listDatabases(projectId);
}

export async function getDatabaseCredentialsFn(opts: { data: { databaseId: string } } | string) {
  const databaseId = typeof opts === "string" ? opts : opts.data.databaseId;
  return getDatabaseCredentials(databaseId);
}

export async function resetDatabasePasswordFn(opts: { data: { databaseId: string; newPassword?: string } } | string) {
  const data = typeof opts === "string" ? { databaseId: opts } : opts.data;
  return resetDatabasePassword(data.databaseId, data.newPassword);
}

export async function deleteDatabaseFn(opts: { data: { databaseId: string } } | string) {
  const databaseId = typeof opts === "string" ? opts : opts.data.databaseId;
  return deleteDatabase(databaseId);
}

export async function createObjectStorageFn(opts: { data: { projectId: string; bucketName: string } }) {
  return createObjectStorage(opts.data);
}

export async function listObjectStoragesFn(opts: { data: string } | string) {
  const projectId = typeof opts === "string" ? opts : opts.data;
  return listObjectStorages(projectId);
}

export async function getStorageCredentialsFn(opts: { data: string } | string) {
  const storageId = typeof opts === "string" ? opts : opts.data;
  return getStorageCredentials(storageId);
}

export async function deleteObjectStorageFn(opts: { data: { id: string } } | string) {
  const storageId = typeof opts === "string" ? opts : opts.data.id;
  return deleteObjectStorage(storageId);
}

export async function executeSqlQueryFn(opts: { data: { databaseId: string; query: string } }): Promise<SqlExecutionResult> {
  return executeSqlQuery(opts.data);
}

export async function listBucketObjectsFn(opts: { data: string } | string): Promise<BucketObject[]> {
  const storageId = typeof opts === "string" ? opts : opts.data;
  return listBucketObjects(storageId);
}

export async function uploadBucketObjectFn(opts: { data: { storageId: string; key: string; content: string; contentType?: string; isBase64?: boolean } }) {
  return uploadBucketObject(opts.data);
}

export async function deleteBucketObjectFn(opts: { data: { storageId: string; key: string } }) {
  return deleteBucketObject(opts.data.storageId, opts.data.key);
}

export async function getObjectContentFn(opts: { data: { storageId: string; key: string } }): Promise<DownloadObjectResult> {
  return getObjectContent(opts.data.storageId, opts.data.key);
}
