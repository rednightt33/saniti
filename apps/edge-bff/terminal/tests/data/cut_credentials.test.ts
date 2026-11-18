/* EXEC-MU-ACCOUNTS Phase 3c (CONTRACT.md 8b "3c in detail", D2 = A): /bundle answers a capped plan's files with a cut on
   this origin (/api/terminal/v1/cut/<T>/<ds>?sha256=), which edge-bff serves only with the session cookie; the storage
   host's presigned URLs keep getting no cookie at all (rack.ts fetchFile, credentialsFor). */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { credentialsFor, fetchFile } from '../../src/data/rack';

afterEach(() => { vi.unstubAllGlobals() });

function recorded() {
  const asked: { url: string, credentials: RequestCredentials | undefined }[] = [];
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    asked.push({ url, credentials:init?.credentials });
    return new Response(new Uint8Array([31, 139, 8, 0]));
  });
  return asked;
}

describe('fetchFile credentials', () => {
  it('a cut on this origin goes with the session cookie (same-origin)', async () => {
    const asked = recorded();
    const url = `/api/terminal/v1/cut/BBCA/price?sha256=${'a'.repeat(64)}`;
    expect(Array.from(await fetchFile(url))).toEqual([31, 139, 8, 0]);
    expect(asked).toEqual([{ url, credentials:'same-origin' }]);
  });
  it('a presigned URL of the storage host goes without any cookie (omit)', async () => {
    const asked = recorded();
    const url = 'https://bucket.t3.storageapi.dev/v1/BBCA/price.json.gz?X-Amz-Signature=abc';
    await fetchFile(url);
    expect(asked).toEqual([{ url, credentials:'omit' }]);
  });
  it('a protocol-relative URL is another host, never sent the cookie', () => {
    expect(credentialsFor('//evil.example/x')).toBe('omit');
    expect(credentialsFor('/api/terminal/v1/cut/BBCA/price')).toBe('same-origin');
  });
});
