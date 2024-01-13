// Compile:
//   javac -classpath <path_to_jar> GMMCalc.java

// Execute:
//   java -classpath <path_to_jar>:. GMMCalc <Mw> <rRup> <vs30> <output_path>
//   e.g.: clear && javac -classpath ../lib/opensha-all.jar GMMCalc.java && java -classpath ../lib/opensha-all.jar:. GMMCalc 7.5 25.00 730.0

// e.g.
// clear && javac -classpath ../lib/opensha-all.jar GMMCalc.java && java -classpath ../lib/opensha-all.jar:. GMMCalc 7.5 25.00 730.0 out.txt

import java.awt.geom.Point2D;

import org.opensha.commons.data.Site;
import org.opensha.commons.data.TimeSpan;
import org.opensha.commons.data.function.ArbitrarilyDiscretizedFunc;
import org.opensha.commons.data.function.DiscretizedFunc;
import org.opensha.commons.geo.Location;
import org.opensha.commons.param.Parameter;
import org.opensha.sha.calc.HazardCurveCalculator;
import org.opensha.sha.earthquake.ERF;
import org.opensha.sha.earthquake.ERF_Ref;
import org.opensha.sha.gui.infoTools.IMT_Info;
import org.opensha.sha.imr.AttenRelRef;
import org.opensha.sha.imr.ScalarIMR;
import org.opensha.sha.imr.attenRelImpl.ngaw2.ASK_2014;
import org.opensha.sha.imr.attenRelImpl.ngaw2.NGAW2_GMM;
import org.opensha.sha.imr.param.IntensityMeasureParams.SA_Param;
import org.opensha.sha.imr.attenRelImpl.ngaw2.IMT;
import org.opensha.sha.imr.attenRelImpl.ngaw2.ScalarGroundMotion;
import static java.lang.Math.exp;

import java.io.File;
import java.io.FileWriter;
import java.io.IOException;


class GMMCalc {

    public static void main(String[] args) {

	double Mw = Double.parseDouble(args[0]);
	double rRup = Double.parseDouble(args[1]);
	double vs30 = Double.parseDouble(args[2]);
	String output_file_path = args[3];

	// ScalarIMR gmm = AttenRelRef.ASK_2014.instance(null);
	NGAW2_GMM gmm = new ASK_2014();

	Double[] periods = new Double[23];
	Double[] savals  = new Double[23];
	Double[] stdvals  = new Double[23];

	int j = 0;
	for (IMT imt : gmm.getSupportedIMTs()) {
	    gmm.set_IMT(imt);
	    gmm.set_Mw(Mw);
	    gmm.set_rRup(rRup);
	    gmm.set_rJB(0.00);
	    gmm.set_rX(0.00);
	    gmm.set_zTop(0.00);
	    gmm.set_zHyp(0.00);
	    gmm.set_vs30(vs30);
	    gmm.set_dip(90.00);
	    gmm.set_width(10.00);
	    ScalarGroundMotion res = gmm.calc();
	    Double period;
	    if (imt.name().startsWith("SA")) {
		period = imt.getPeriod();
		periods[j] = period;
		savals[j] = exp(res.mean());
		stdvals[j] = res.stdDev();
		j++;
	    }
	    if (imt.name().startsWith("PGA")) {
		period = 0.00;
		periods[j] = period;
		savals[j] = exp(res.mean());
		stdvals[j] = res.stdDev();
		j++;
	    }

	}
	
	// write results to a text file
	try {
	    File myObj = new File(output_file_path);
	    if (myObj.createNewFile()) {
		System.out.println("File created: " + myObj.getName());
	    } else {
		// file already exists
		myObj.delete();
		myObj.createNewFile();
		System.out.println("File replaced: " + myObj.getName());
	    }
	} catch (IOException e) {
	    System.out.println("An error occurred.");
	    e.printStackTrace();
	}
	try {
	    FileWriter myWriter = new FileWriter(output_file_path);
	    for (int i = 0; i < periods.length; i++) {
		myWriter.write(String.valueOf(periods[i])+", "+String.valueOf(savals[i])+", "+String.valueOf(stdvals[i])+"\n");
	    }
	    myWriter.close();
	} catch (IOException e) {
	    System.out.println("An error occurred.");
	    e.printStackTrace();
	}

    }

}
