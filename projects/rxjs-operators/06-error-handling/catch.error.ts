// 06-error-handling/catch.error.ts
// Handles errors in an Observable sequence
// 
// pnpm exec ts-node 06-error-handling/catch.error.ts

import { catchError, map, of } from "rxjs";

of(1, 2, 3).pipe(
  map(x => { if (x === 2) throw new Error('Error!'); return x; }),
  catchError(err => of('Recovered:', err))
).subscribe(console.log);