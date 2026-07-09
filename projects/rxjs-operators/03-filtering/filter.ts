// 03-filtering/filter.ts
// Filters emitted values based on a predicate
//
// pnpm exec ts-node 03-filtering\filter.ts

import { filter, of } from "rxjs";

of(1, 2, 3, 4).pipe(filter(x => x % 2 === 0)).subscribe(console.log)