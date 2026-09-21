#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "numtools.h"
#include "defs.h"
#include "init.h"

/* Set debugging flag */
//#define DEBUG

/* Prototypes not included in header files */
void derivs(double t, double *yin, double *yout);
void init_derivs(void);
  
/* Prototypes for functions defined in this file */
void readIcs(char *file, double *varArray);
void saveLast(char *fname, int numVars, char *varNameArray[], double *varArray);
void swap(double **a, double **b);
void PrintOutput(double t, double dt, double *yout, int numouts, int *outvarindices, int numkeeps, int *keepvarindices, char *varNameArray[]);
void readOutvars(char *file, int *varArray, int *numouts, int *varArray2, int *numouts2);
int getVarNameIndex(char *varName);
void findCurrentName(char *Vname, char *Iname);

double *vc;
extern double P[];
extern double G[];
extern char N[][LEN];
//char **N;

int main (int argc, char **argv)
{
	FILE *fout, *flast;
	char *ics = 0;
	char *varfile = 0;
	double *yin, *yout, last[NUMODES];
	double t = T_START, t_end = T_END, dt = DT, tolerance = UNDEF;
	int skip = SKIP;
	long i = 0, j, numrows;
	int n = 0;
 	int no_steps;
	double new_dt;
	int numouts=UNDEF;
	int outvarindices[NUMODES];
	int numkeeps=UNDEF;
	int tt=0;
#ifdef NUMKEEPS
	int keepvarindices[NUMKEEPS];
#else
	int keepvarindices[1];
#endif

	yin = vector(NUMODES);
	yout = vector(NUMODES);
#ifdef VOLTAGE_CLAMP
	vc = vector(NUMVCS);
#endif
	for (i = 1; i < argc; i++) {
	  /*
	   *	Handle command-line options
	   */
	  if (argv[i][0] == '-') {
	    switch(argv[i][1]) {
	    case 'b':	       	 /* begin time option */
	      t = atof(argv[i]+2);
	      break;
	    case 'e':  		 /* end time option */
	      t_end = atof(argv[i]+2);
	      break;
	    case 'h':            /* size of dt option */
	      dt = atof(argv[i]+2);
	      break;
	    case 's':		 /* skip value for printing output */
	      skip = atoi(argv[i]+2);
	      break;
	    case 't':		/* tolerance for variable timestep */
	      tolerance = atof(argv[i]+2);
	      break;
	    case 'k':		/* read output variables */
	      varfile=argv[i]+2;
	      break;
	    default:	      	/* unknown option error message */
	      fprintf(stderr, "Unknown command '%c'\n", argv[i][1]);
	      break;
	    }
	  } else
	    ics = argv[i];    	/* set ics filename to arg name */
	}

	/* Initialize variables with ics file, if provided */
	if (ics != NULL)
		readIcs(ics, yin);
	if(strlen(varfile) > 0)
	{
	  numkeeps=0;
	  readOutvars(varfile, outvarindices, &numouts, keepvarindices, &numkeeps);
	}
	  
#ifdef DEBUG
	fprintf(stderr,"number of output variables=%d\n", numouts);
#endif
	/* include the vals from the .networkpars file into the params */
	init_derivs();

	
	//Farzan commented this line. It seems unnecessary and
	//screws up the alpha function
	//	t += dt;     
	t_end -= dt;
#ifdef DEBUG
	fprintf (stderr, "tolerance=%f\n", tolerance);
#endif
	if(tolerance>0)
	  adaptive_rk(t, t_end, dt, NUMODES, yin, yout, .01, derivs);	
	else
	{
	  // v1.4:
	  PrintOutput(-1, dt, yout, numouts, outvarindices, numkeeps, keepvarindices, Vars);
	  //Farzan changed this in v1.4:
	  //  	for (i = 1; t < t_end; t += dt, i++)
  	for (i = 0; t < t_end; t += dt, i++)
	{
	  if(i>0) First=FALSE;
#ifdef VERBATIM
	  Verbatim(t,i,yin);
#endif
//farzan 200411:
//#ifdef NODES
//	  update_nodes(t, yin);
//#endif
	  rk4(t, dt, NUMODES, yin, yout, derivs);
#ifdef VOLTAGE_CLAMP
	  vclampI(t, yin, vc);
#endif
	  if (i % skip == 0)
	     PrintOutput(t, dt, yout, numouts, outvarindices, numkeeps, keepvarindices, Vars);
	  swap(&yin, &yout);
	}

	/*	Save last values of variables */
	rk4(t, dt, NUMODES, yin, yout, derivs);
	}
	saveLast("last", NUMODES, Vars, yin);
	return 0;                                                                                                                                             			
}

/************************** Functions ***************************/

void readIcs(char *file, double *varArray)
{
  FILE	*ics;
  char	lineBuffer[LEN];
  char	*equalsSignPtr;
  char	varName[LEN];
  double	val;
  int	varNameIndex;
  
  ics = fopen(file, "r");
  if (ics == NULL) {
    fprintf(stderr, "Cannot open '%s' for reading.\n", file);
    exit (1);
  }	
  
  while(fgets(lineBuffer, sizeof(lineBuffer), ics) != NULL) {
    equalsSignPtr = strchr(lineBuffer, '=');
    if (equalsSignPtr != NULL)
      *equalsSignPtr = ' ';	
    /*
       WARNING: As val is type double, it MUST be scanned
       with "%lf". Any other type-conversion will fail.
     */
    sscanf(lineBuffer, "%s %lf\n", varName, &val);
    varNameIndex = getVarNameIndex(varName);
    if (varNameIndex == -1) {
      fprintf(stderr, "Error: variable name '%s' is not defined\n",
	      varName);
      //      exit(2);
    }
    else
      varArray[varNameIndex] = val;
  }

  fclose(ics);
}

////////////////////////////////////////////////////////////////////
void readOutvars(char *file, int *varArray, int *numouts, int *varArray2, int *numouts2)
{
  FILE	*var;
  char	varname[LEN];
  int	varNameIndex;
  
  var = fopen(file, "r");
  *numouts=0;
  if (var == NULL) {
    fprintf(stderr, "Cannot open '%s' for reading.\n", file);
    exit (1);
  }	
  
  while(fscanf(var, "%s", varname) > 0 ) {
    varNameIndex = getVarNameIndex(varname);
    //fprintf(stderr,"varname=%s varNameIndex=%d\n", varname, varNameIndex);
    if (varNameIndex == -1) {
      fprintf(stderr, "Error: variable name '%s' is not defined\n",
	      varname);
      exit(2);
    }
    else if (varNameIndex >= 0)
      varArray[(*numouts)++] = varNameIndex;
    else 
      varArray2[(*numouts2)++] = -varNameIndex-2; 
  }
  
  fclose(var);
}

////////////////////////////////////////////////////////////////////

/////////////////////////////////////////////////////////////////////////

int getVarNameIndex(char *varName)
{
    int i, r, match;

    for (i = 0; i < NUMODES; i++) {
      match=strcmp(Vars[i], varName);
        if(match == 0)
	  {
	    r=i;
            break;
	  }
    }

    if (i == NUMODES)   /* if no match was found */
    {
#ifdef NUMKEEPS
      
      for (i = 0; i < NUMKEEPS; i++) {
	if(strcmp(Keeps[i], varName) == 0)
	  {
	    r=-2-i;
            break;
	  }
      } 
      if (i == NUMKEEPS)   /* if no match was found */
#endif
        r=-1;      /* return error value */
    }

    return r;
}

////////////////////////////////////////////////////////////////////

void saveLast(char *fname, int numVars, char *varNameArray[], double *varArray)
{
	int		i;
	FILE	*flast;

	flast = fopen(fname, "w");
	if (flast == NULL) {
		fprintf(stderr, "Cannot save last values to file '%s'.\n", fname);
		exit (1);
	}

	for (i = 0; i < numVars; i++)
		fprintf(flast, "%s=%f\n", varNameArray[i], varArray[i]);

	fclose(flast); 
}

////////////////////////////////////////////////////////////////////

void swap(double **a, double **b)
{
    double *tmp;

    tmp = *a;
    *a = *b;
    *b = tmp;                                                                  
}
////////////////////////////////////////////////////////////////////
// This function was modified in version 1.4 to print the names
// of variables on the first line of output
void PrintOutput(double t, double dt, double *yout, int numouts, int *outvarindices, int numkeeps, int *keepvarindices, char *varNameArray[]) 
{
  int j;
#ifdef VOLTAGE_CLAMP
  char currentName[LEN]="I";
#endif

  if(t < -0.5) // i.e. t=-1
  {
    printf ("#t");
    if(numouts < 0)
      for (j = 0; j < NUMODES; j++)
	printf(" #%s", varNameArray[j]);
    else
      for(j = 0; j < numouts; j++)
	printf(" #%s", varNameArray[outvarindices[j]]);
  }    
  else
    {
      // v 1.4:      printf("%f", t+dt);
      printf("%f", t);
      if(numouts < 0)
	for (j = 0; j < NUMODES; j++)
	  printf(" %.8f", yout[j]);
      else
	for(j = 0; j < numouts; j++)
	  printf(" %.8f", yout[outvarindices[j]]);
    }
#ifdef NUMKEEPS
  //    fprintf(stderr,"NUMKEEPS=%d numkeeps=%d\n", NUMKEEPS,numkeeps);
  if(t < -0.5) // i.e. t=-1
    {
      if(numkeeps < 0)
	for (j = 0; j < NUMKEEPS; j++)
	  printf(" #%s", Keeps[j]);
      else
	for(j = 0; j < numkeeps; j++)
	  printf(" #%s", Keeps[keepvarindices[j]]);
    }
  else
    {
      if(numkeeps < 0)
	for (j = 0; j < NUMKEEPS; j++)
	  printf(" %.8f", G[j]);
      else
	for(j = 0; j < numkeeps; j++)
	  printf(" %.8f", G[keepvarindices[j]]);
    }
#endif

#ifdef VOLTAGE_CLAMP
  for (j = 0; j < NUMVCS; j++)
      if(t < -0.5 ) // i.e. t=-1
	{
	  	  findCurrentName(N[VC_num[j]], currentName);
	  	  printf(" #%s", N[VC_num[j]]);
	  	  printf(" #%s", currentName);
	}
      else
	{
	  printf(" %.8f", P[VC_num[j]]);
	  printf(" %.8f", vc[j]);
	}
#endif
  printf("\n");
}
////////////////////////////////////////////////////////////////////
void findCurrentName(char *Vname, char *Iname)
{
  int l;
    l=strlen(Vname);

    strcpy(Iname,Vname);
    Iname[l-2] = 'I';
    Iname[l-1] = '\0';
}
