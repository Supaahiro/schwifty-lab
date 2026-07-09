// 02-transformation/buffer-count.ts
// Buffers values into arrays of a specified size
//
// pnpm exec ts-node 02-transformation\buffer-count.ts

import { bufferCount, of } from "rxjs";

of(1, 2, 3, 4, 5).pipe(bufferCount(2)).subscribe(console.log)