// 04-combination/zip.ts
// Combines values from multiple Observables based on their index
//
// pnpm exec ts-node 04-combination/zip.ts

import { of, zip } from 'rxjs';

zip(of('a', 'b', 'c'), of(1, 2, 3)).subscribe(console.log);