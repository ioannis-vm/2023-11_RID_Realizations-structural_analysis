// Compile:
//   javac -classpath <path_to_jar> DisaggregationCalc.java

// Execute:
// java -classpath <path_to_jar>:. DisaggregationCalc <period> <latitude> <longitude> <vs30> <imlVal>

// e.g.
// clear && javac -classpath ../../external_tools/opensha-all.jar DisaggregationCalc.java && java -classpath ../../external_tools/opensha-all.jar:. DisaggregationCalc 1.00 37.871 -122.259 733.4 0.20 out.txt

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


class DisaggregationCalc {

    public static void main(String[] args) {

	double input_period = Double.parseDouble(args[0]);
	double latitude = Double.parseDouble(args[1]);
	double longitude = Double.parseDouble(args[2]);
	double vs30 = Double.parseDouble(args[3]);
	double imlVal = Double.parseDouble(args[4]);
	String output_file_path = args[5];
	
	// choose an ERF, easy way is from the ERF_Ref enum (which contains all of them used in our apps):
	ERF erf = (ERF)ERF_Ref.MEAN_UCERF3.instance(); // casting here makes sure that it's a regular ERF and not an epistemic list erf
		
	// System.out.println("ERF: "+erf.getName());
	// let's view the adjustable parameters
	// System.out.println("ERF Params");
	for (Parameter<?> param : erf.getAdjustableParameterList())
	    System.out.println("\t"+param.getName()+": "+param.getValue());
	// same for the time span
	TimeSpan timeSpan = erf.getTimeSpan();
	// System.out.println("Default Duration: "+timeSpan.getDuration());
		
	// if you want to change any parameters or the time span, do them now

	timeSpan.setDuration(1.00);
	System.out.println("Updated Duration: "+timeSpan.getDuration());
		
	// finally, call the updateForecast() method which builds the forecast for the current set of parameters
	// System.out.println("Updating forecast...");
	erf.updateForecast();
	// System.out.println("DONE updating forecast");
		
	// now choose a GMM, easiest way is from the AttenRelRef enum
	ScalarIMR gmm = AttenRelRef.NGAWest_2014_AVG.instance(null);
		
	System.out.println("GMM: "+gmm.getName());
		
	// set paramter defaults
	gmm.setParamDefaults();
		
	// set the intensity measure type
	gmm.setIntensityMeasure(SA_Param.NAME);
		
	// if SA, set the period
	SA_Param.setPeriodInSA_Param(gmm.getIntensityMeasure(), input_period);
		
	// build a site
	Site site = new Site(new Location(latitude, longitude));
	System.out.println("Site location: "+site.getLocation());
		
	gmm.getSiteParams().setValue("vs30", vs30);
	System.out.println(gmm.getSiteParams());

	for (Parameter<?> param : gmm.getSiteParams()) {
	    site.addParameter(param);
	}
		
	// create a hazard curve calculator
	HazardCurveCalculator calc = new HazardCurveCalculator();
		
	DisaggregationCalculatorAPI disaggCalc;
	disaggCalc = new DisaggregationCalculator();

	boolean disaggSuccessFlag = disaggCalc.disaggregate(Math.log(imlVal),
							    site, gmm, (AbstractERF) erf,
							    calc.getAdjustableParams());
	String disaggregationString = disaggCalc.getMeanAndModeInfo();
	System.out.println(disaggregationString);

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
	    myWriter.write(""+disaggregationString+"\n");
	    myWriter.close();
	} catch (IOException e) {
	    System.out.println("An error occurred.");
	    e.printStackTrace();
	}

	
    }

}
