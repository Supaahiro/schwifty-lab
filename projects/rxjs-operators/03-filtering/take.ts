// 03-filtering/filter.ts
// Emits only the first n values
//
// pnpm exec ts-node 03-filtering\take.ts

import { interval, take } from "rxjs";

interval(100).pipe(take(3)).subscribe(console.log)