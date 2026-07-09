// 06-error-handling/retry.ts
// Retries an Observable sequence a specified number of times upon error
//
// pnpm exec ts-node 06-error-handling/retry.ts

import { catchError, map, of, retry } from "rxjs";

of(1, 2, 3).pipe(
  map(x => { if (x === 2) throw new Error('fail'); return x; }),
  retry(2),
  catchError(() => of('Failed after retries'))
).subscribe(console.log);