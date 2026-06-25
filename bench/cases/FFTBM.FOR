      PROGRAM FFTBM
C     Numeric workload: forward+inverse FFT of a 256-point array, repeated.
C     Links with demos/FFT.FOR (Singleton mixed-radix FFT).
      COMMON /O/ R
      DIMENSION A(256), B(256)
      DO 5 I = 1, 256
         A(I) = SIN(FLOAT(I))
         B(I) = 0.0
    5 CONTINUE
      DO 20 K = 1, 100
         CALL FFT(A, B, 256, 256, 256, 1)
         CALL FFT(A, B, 256, 256, 256, -1)
   20 CONTINUE
      R = A(1)
      END
