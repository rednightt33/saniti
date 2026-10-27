/* Registers resolve.mjs for this process: `node --experimental-strip-types --import ./loader/register.mjs ...`, as the
   image's command and every npm script that runs the worker's TypeScript do (README "Run"). */
import { register } from 'node:module';

register('./resolve.mjs', import.meta.url);
