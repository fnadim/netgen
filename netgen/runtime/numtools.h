void rk4(double t, double dt, int n, double *y, double *yout,
                                   void (*derivs)(double, double *, double *));
void adaptive_rk(double t, double t_end, double dt, int n, double *y, double *yout, double tol, void (*derivs)(double, double *, double *));
void vclampI(double t , double *yin, double *vc);
double power(double base, unsigned int exponent);
double *vector(long dim);
double **matrix(long nrows, long ncols);
double alpha(double tau, double t);
double AlphaSyn(double tau, double lastSpike, double tolerance, double t);
double pulseStim(double period, double onTime, double stimAmp, double t);
double controlledPulse(double t, double appliedI, double testVoltage,
			double threshold, double delay, double isInSync);
int threshold_crossed(double testVoltage, double threshold, double slope);
int isIntegerMultiple(double t, double period, double tolerance);
int isEqual(double a, double b, double tolerance);
int isGreater(double a, double b, double tolerance);
int isLesser(double a, double b, double tolerance);
void memerr(void);

#define FALSE 0
#define TRUE 1
#define ARRAYSIZE 20
#define NUMTAUSTODECAY 15
/* Default Option values */
#define T_START 0.0
#define T_END 100.0
#define DT 0.1
#define SKIP 1
// #define LEN 256 // now in defs.h
#define UNDEF -1

