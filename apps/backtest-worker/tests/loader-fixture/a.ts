// loader.test.ts: a module that imports its neighbours as the Terminal's sources do, without an extension
import { b } from './b';
import { c } from './dir';
export const a = b + c;
