// Compile:
//   javac -classpath <path_to_jar> HazardCurveCalc.java

// Execute:
// java -classpath <path_to_jar>:. HazardCurveCalc <period> <latitude> <longitude> <vs30>

// e.g.
// clear && javac -classpath ../lib/opensha-all.jar HazardCurveCalc.java && java -classpath ../lib/opensha-all.jar:. HazardCurveCalc 1.00 37.871 -122.259 733.4 out.txt

import java.awt.geom.Point2D;
import org.opensha.commons.data.Site;
import org.opensha.commons.data.TimeSpan;
import org.opensha.commons.data.function.ArbitrarilyDiscretizedFunc;
import org.opensha.commons.data.function.DiscretizedFunc;
import org.opensha.commons.geo.Location;
import org.opensha.commons.param.Parameter;
import org.opensha.sha.calc.HazardCurveCalculator;
import org.opensha.sha.calc.disaggregation.DisaggregationCalculator;
import org.opensha.sha.calc.disaggregation.DisaggregationCalculatorAPI;
import org.opensha.sha.earthquake.AbstractERF;
import org.opensha.sha.earthquake.ERF;
import org.opensha.sha.earthquake.ERF_Ref;
import org.opensha.sha.gui.infoTools.IMT_Info;
import org.opensha.sha.imr.AttenRelRef;
import org.opensha.sha.imr.ScalarIMR;
import org.opensha.sha.imr.param.IntensityMeasureParams.SA_Param;

import java.io.File;
import java.io.FileWriter;
import java.io.IOException;

class HazardCurveCalc {

    public static void main(String[] args) {

	double input_period = Double.parseDouble(args[0]);
	double latitude = Double.parseDouble(args[1]);
	double longitude = Double.parseDouble(args[2]);
	double vs30 = Double.parseDouble(args[3]);
	String output_file_path = args[4];

	// choose an ERF, easy way is from the ERF_Ref enum (which contains all of them used in our apps):
	ERF erf = (ERF)ERF_Ref.MEAN_UCERF3.instance(); // casting here makes sure that it's a regular ERF and not an epistemic list erf
		
	// same for the time span
	TimeSpan timeSpan = erf.getTimeSpan();
	timeSpan.setDuration(1.00);
		
	// finally, call the updateForecast() method which builds the forecast for the current set of parameters
	erf.updateForecast();
		
	// now choose a GMM, easiest way is from the AttenRelRef enum
	ScalarIMR gmm = AttenRelRef.NGAWest_2014_AVG.instance(null);
		
	// set paramter defaults
	gmm.setParamDefaults();
		
	// set the intensity measure type
	gmm.setIntensityMeasure(SA_Param.NAME);
		
	// if SA, set the period
	SA_Param.setPeriodInSA_Param(gmm.getIntensityMeasure(), input_period);
		
	// build a site
	Site site = new Site(new Location(latitude, longitude));
		
	gmm.getSiteParams().setValue("vs30", vs30);

	for (Parameter<?> param : gmm.getSiteParams()) {
	    site.addParameter(param);
	}
		
	// create a hazard curve calculator
	HazardCurveCalculator calc = new HazardCurveCalculator();
		
	// get default x-values for hazard calculation
	DiscretizedFunc xVals = new IMT_Info().getDefaultHazardCurve(gmm.getIntensityMeasure());
		
	// create the same but in ln spacing
	DiscretizedFunc lnXVals = new ArbitrarilyDiscretizedFunc();
	for (Point2D pt : xVals)
	    lnXVals.set(Math.log(pt.getX()), 1d);
		
	// calculate curve, will fill in the y-values from the above
	calc.getHazardCurve(lnXVals, site, gmm, erf);
		
	// now combine those y values with the original linear x values
	DiscretizedFunc curve = new ArbitrarilyDiscretizedFunc();
	for (int i=0; i<xVals.size(); i++)
	    curve.set(xVals.getX(i), lnXVals.getY(i));

	// write results to a text file
	try {
	    File myObj = new File(output_file_path);
	    if (myObj.createNewFile()) {
		System.out.println("File created: " + myObj.getName());
	    } else {
		// file already exists
		myObj.delete();
		myObj.createNewFile();
	    }
	} catch (IOException e) {
	    System.out.println("An error occurred.");
	    e.printStackTrace();
	}
	try {
	    FileWriter myWriter = new FileWriter(output_file_path);
	    for (Parameter<?> param : erf.getAdjustableParameterList())
		myWriter.write("\t"+param.getName()+": "+param.getValue());
	    myWriter.write("Updated Duration: "+timeSpan.getDuration());
	    myWriter.write("GMM: "+gmm.getName());
	    myWriter.write("Site location: "+site.getLocation());
	    myWriter.write(""+gmm.getSiteParams());
	    myWriter.write("Hazard curve:\n"+curve);
	    myWriter.close();
	} catch (IOException e) {
	    System.out.println("An error occurred.");
	    e.printStackTrace();
	}

    }

}
