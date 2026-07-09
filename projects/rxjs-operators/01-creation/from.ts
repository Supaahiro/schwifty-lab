// 01-creation/from.ts
// Convert array, Promise or iterable to stream
// 
// pnpm exec ts-node 01-creation\from.ts

import { from } from "rxjs";

from([10, 20, 30]).subscribe(console.log)