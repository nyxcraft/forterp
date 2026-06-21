C     ==================================================================
C     EXAMPLE3 -- driver for R. C. Singleton's archival 1968 FFT.
C     Transforms an eight-point impulse, then recovers the input data.
C     ==================================================================
      PROGRAM FFTDEM
      REAL A(8), B(8)
      INTEGER I
      DO 10 I=1,8
      A(I)=0.0
      B(I)=0.0
   10 CONTINUE
      A(1)=1.0
      CALL FFT(A,B,8,8,8,1)
      WRITE(6,20)
   20 FORMAT(18H FORWARD TRANSFORM)
      DO 30 I=1,8
      WRITE(6,40) I,A(I),B(I)
   30 CONTINUE
   40 FORMAT(1X,I3,2F12.6)
      CALL FFT(A,B,8,8,8,-1)
      WRITE(6,50)
   50 FORMAT(18H RECOVERED IMPULSE)
      DO 60 I=1,8
      A(I)=A(I)/8.0
      B(I)=B(I)/8.0
      WRITE(6,40) I,A(I),B(I)
   60 CONTINUE
      END
