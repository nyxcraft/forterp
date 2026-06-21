C     ==================================================================
C     EXAMPLE1 -- driver for the genuine 1976 EISPACK library (EISPACK.FOR).
C     Finds the eigenvalues of a 4x4 symmetric tridiagonal matrix via RS
C     (-> TRED2 -> TQL2 -> PYTHAG).  Plain ANSI FORTRAN 66.
C     Run (linking the library alongside this driver):
C         python -m forterp EXAMPLE1.FOR EISPACK.FOR
C     Expected eigenvalues 2-2cos(k*pi/5): 0.38197 1.38197 2.61803 3.61803
C     ==================================================================
      PROGRAM EIGEN
      INTEGER NM, N, MATZ, IERR, I
      DOUBLE PRECISION A(4,4), W(4), Z(4,4), FV1(4), FV2(4)
      DATA A /2.,-1.,0.,0., -1.,2.,-1.,0., 0.,-1.,2.,-1., 0.,0.,-1.,2./
      NM = 4
      N = 4
      MATZ = 1
      CALL RS(NM, N, A, W, MATZ, Z, FV1, FV2, IERR)
      WRITE(6,10) IERR
   10 FORMAT(7H IERR =, I3)
      WRITE(6,20) (W(I), I = 1, 4)
   20 FORMAT(14H EIGENVALUES: , 4F10.5)
      END
