      PROGRAM LOOP
C     Tight interpreter-loop microkernel: raw per-statement overhead.
      COMMON /O/ R
      DOUBLE PRECISION X
      X = 0.0D0
      DO 10 I = 1, 1000000
         X = X + 1.0D0
   10 CONTINUE
      R = X
      END
