// 02-transformation/map.ts
// Transforms emitted values
//
// pnpm exec ts-node 02-transformation\map.ts

import { map, of } from "rxjs";

of(1, 2, 3).pipe(map(x => x * 10)).subscribe(console.log)