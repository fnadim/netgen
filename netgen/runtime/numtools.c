#include <stdlib.h>
#include <stdio.h>
#include <math.h>
#include "numtools.h"
#include "defs.h"

#define min(X, Y) (((X) < (Y)) ? (X):(Y))
#define absVal(X) (((X) > 0) ? (X):-(X))
#define FLOOR(X) ((int)(X))
#define CEIL(X) (1+(int)(X))
#define ROUND(X) ((int)((X)+0.5))
extern double *vc, P[];
extern int VC_num[];
void swap(double **a, double **b);

void rk4(double t, double dt, int n, double *y, double *yout,
					void (*derivs)(double, double *, double *))
{
	int i;
	double *k1, *k2, *k3, *k4;
	double *yt;

	k1 = vector(n);	
	k2 = vector(n);	
	k3 = vector(n);	
	k4 = vector(n);	

	yt = vector(n);


	(*derivs)(t, y, k1);

	for (i = 0; i < n; i++)
		yt[i] = y[i] + dt*k1[i] / 2.0;

	(*derivs)(t+dt/2.0, yt, k2);

	for (i = 0; i < n; i++)
		yt[i] = y[i] + dt*k2[i] / 2.0;

	(*derivs)(t+dt/2.0, yt, k3);

	for (i = 0; i < n; i++)		
		yt[i] = y[i] + dt*k3[i];

	(*derivs)(t+dt, yt, k4);

	for (i = 0; i < n; i++)
		yout[i] = y[i] + dt*(k1[i] + 2.0*k2[i] + 2.0*k3[i] + k4[i]) / 6.0;

	free(k1);
	free(k2);
	free(k3);
	free(k4);
	free(yt);
}

void rk6(double t, double h, int n, double *y, double *y_b, double *R,
					void (*derivs)(double, double *, double *))
{
   	int i;
	int j;
	double *k1, *k2, *k3, *k4, *k5, *k6;
        double *y_temp;
        double  t_temp;
        double *func_temp;
        k1 = vector(n);
        k2 = vector(n);
        k3 = vector(n);
        k4 = vector(n);
        k5 = vector(n);
        k6 = vector(n);
        y_temp = vector(n);
        func_temp = vector(n);

        (*derivs)(t, y, func_temp);
 	
 	for(i=0; i<n; i++)
        {
        		k1[i]=h*func_temp[i];
        }

        for(i=0; i<n; i++)
        y_temp[i] = y[i] + 0.25*k1[i];
        t_temp=t + 0.25*h;
        (*derivs)(t_temp, y_temp, func_temp);
        for(i=0; i<n; i++)
        {
        	k2[i]=h*func_temp[i];
        }

       	for(i=0; i<n; i++)
        	y_temp[i] = y[i] + (3.0/32.0)*k1[i] + (9.0/32.0)*k2[i];
        t_temp=t + (3.0/8.0)*h;
	(*derivs)(t_temp, y_temp, func_temp);
       	for(i=0; i<n; i++)
       	{
        	k3[i]=h*func_temp[i];
        }
	
	for(i=0; i<n; i++)
	        y_temp[i] = y[i] + (1932.0/2197.0)*k1[i] - (7200.0/2197.0)*k2[i] + (7296.0/2197.0)*k3[i];
        t_temp=t + (12.0/13.0)*h;
	(*derivs)(t_temp, y_temp, func_temp);
        for(i=0; i<n; i++)
	{
	       	k4[i]=h*func_temp[i];
        }

        for(i=0; i<n; i++)
	        y_temp[i] = y[i] + (439.0/216.0)*k1[i] - 8.0*k2[i] + (3680.0/513.0)*k3[i] - (845.0/4104.0)*k4[i];
	t_temp=t + h;

	(*derivs)(t_temp, y_temp, func_temp);
        for(i=0; i<n; i++)
        	k5[i]=h*func_temp[i];

        for(i=0; i<n; i++)
	        y_temp[i] = y[i] - (8.0/27.0)*k1[i] + 2.0*k2[i] - (3544.0/2565.0)*k3[i] + (1859.0/4104.0)*k4[i] - (11.0/40.0)*k5[i];
	t_temp=t + 0.5*h;

	(*derivs)(t_temp, y_temp, func_temp);
        for(i=0; i<n; i++)
        	k6[i]=h*func_temp[i];


        for(i=0;i<n;i++)
   		{
   			R[i] = (1.0/h)* ( (1.0/360.0)*k1[i] - (128.0/4275.0)*k3[i] - (2197.0/75240.0)*k4[i] + (1.0/50.0)*k5[i] + (2.0/55.0)*k6[i]);
   			y_b[i] = y[i] + (25.0/216.0)*k1[i] + (1408.0/2565.0)*k3[i] + (2197.0/4104.0)*k4[i] - (0.2)*k5[i];
       		 }
       	
	free(k1);
	free(k2);
	free(k3);
	free(k4);
	free(k5);
     	free(k6);
	free(y_temp);
	free(func_temp);
}

double Err(double *R, int n)
{
	double temp;
	int i;
	temp=0.0;
        for(i=0; i<n; i++)
        {
		temp = temp + pow(R[i], 2);
	}
	return pow(temp, 0.5);
}


void adaptive_rk(double t, double t_end, double dt, int n, double *y, double *yout, double tol,
					void (*derivs)(double, double *, double *))

{
   	int i, j;
	double h;
  	double Error, delta;
	int counter, temp;
	double *R;
   	double *y_b;
   	h=dt;
	counter=0;
	temp=0;
	y_b = vector(n);
        R   = vector(n);

        while(t<t_end)
        {
        	rk6(t, h, n, y, y_b, R, derivs);	
        	Error = Err(R,n);

        	//if(Error>tol&&h>0.001)
        	//{
        	
	        	delta = 0.84*pow((tol/Error), 0.25);	
			
			if(delta<=0.1)
        			h=h*0.1;
        		else if(delta>=4.0)
        			h=h*4.0;
        		else h=h*delta;
        			
        	//}
		t=t+h;

		for(i=0; i<n; i++)
        	{
        		yout[i]=y_b[i];
        	}

        	if(counter==temp)
		{
		
        	printf("%f\t", t);
        	for (i = 0; i < n; i++)
        		printf(" %f\t", yout[i]);
#ifdef VOLTAGE_CLAMP
			vclampI(t, y, vc);
			for (j = 0; j < NUMVCS; j++)
			{
			 printf(" %f", P[VC_num[j]]);
			 printf(" %f", vc[j]);
			}
#endif
        	printf("\n");
        	temp=temp+5;
		}
		swap(&y, &yout);
		counter++;
        }     		
 }


double power(double base, unsigned int exponent)
{
	if (exponent == 0)
		return 1;
	else
		return base * power(base, exponent-1);
}

double *vector(long dim)
{
	double *v;
	v = (double *) malloc(dim * sizeof(double));
	if (!v) memerr();

	return v;
}

double **matrix(long nrows, long ncols)
{
	double	**m;
	long	i;

	m = (double **) malloc(nrows * sizeof(double *));
	if (!m) memerr();

	for (i = 0; i < nrows; i++) {
		m[i] = (double *) malloc(ncols * sizeof(double));
		if (!m[i]) memerr();
	}

	return m;
}

double alpha(double tau, double t)
{
	return (t/tau)*exp(1-(t/tau));
}

double AlphaSyn(double tau, double lastSpike, double tolerance, double t)
{
	int i;
	static int n = 0;
	static double SpikeArray[ARRAYSIZE];
	double val = 0.0;

	if(n==(int) (1.5*ARRAYSIZE)) n -= ARRAYSIZE;
	if(lastSpike >= 0)
	if ((n == 0) ||
		(!isEqual(lastSpike, SpikeArray[(n-1)%ARRAYSIZE], tolerance)))
	  SpikeArray[(n++)%ARRAYSIZE] = lastSpike;
	//	  fprintf(stderr,"lastSpike=%.2f n=%d\n",lastSpike,n);}
	for (i = 0; i < min(n,ARRAYSIZE); i++)	
	  if( t < SpikeArray[i]+NUMTAUSTODECAY*tau )
	    val += alpha(tau, t - SpikeArray[i]);
	
	return val;
}

double pulseStim(double period, double onTime, double stimAmp, double t)
{
    double phase;

    // Establish phase
    if (t > 0)
        phase = t - FLOOR(t/period) * period;
    else
        phase = t + CEIL(-t/period) * period;

    // Apply signature of periodic function
    if (phase < onTime)
        return stimAmp;
    else
        return 0;
}

int isIntegerMultiple(double t, double period, double tolerance)
{
	if (absVal(t-period*((int)(t/period+0.5))) < tolerance)
		return TRUE;
	else
		return FALSE;
}

int isEqual(double a, double b, double tolerance)
{
	if (absVal(a - b) < tolerance)
		return TRUE;
	else
		return FALSE;
}

int isGreater(double a, double b, double tolerance)
{
	if((a - b) > tolerance)
		return TRUE;
	else
		return FALSE;
}

int isLess(double a, double b, double tolerance)
{
	if((b - a) < tolerance)
		return TRUE;
	else
		return FALSE;
}

void memerr(void)
{
	fprintf(stderr, "Out of memory\n");
	exit (8);
}

/* Auxillary function for controlledPulse */
int compare(double x, double y, int logicSense)
{
	if (logicSense == 0)	//	for FALSE condition of 'controlledPulse'
		return (x < y);
	else					//	for TRUE condition of 'controllledPulse'
		return (x > y); 
}

double controlledPulse(double t, double appliedI, double testVoltage,
			double threshold, double delay, double isInSync)
{
	static double	delayOnset;
	static int		applyStim = TRUE;
	int				thresholdCrossed;
	int				compare(double x, double y, int logicSense);

	/*
	 *	NOTE:	'isInSync' was prototyped as type 'double' to be read
	 *  properly into the array of doubles 'Var' of the parse_network 
	 *  parser. It must be cast into an integer to be used as a logic
	 *  variable by the 'compare' function.
	 */
	thresholdCrossed = compare(testVoltage, threshold, (int)(isInSync+0.5));

	if (!applyStim && thresholdCrossed) {
		delayOnset = t;
		applyStim = TRUE;
	} else if (!thresholdCrossed)
		applyStim = FALSE;
		
	if (applyStim && (t > (delayOnset + delay) ) )
		return appliedI;
	else
		return 0;
}
////////////////////////////////////////////////////////////
int threshold_crossed(double testVoltage, double threshold, double slope)
{
  static double	oldVoltage;
  int thresholdCrossed;

  thresholdCrossed = ( (testVoltage >= threshold) && (oldVoltage < threshold) && slope > 0 ) || ( (testVoltage <= threshold) && (oldVoltage > threshold) && slope < 0 );
  oldVoltage = testVoltage;
  
  if (thresholdCrossed) 
    return TRUE;
  else
    return FALSE;
}
