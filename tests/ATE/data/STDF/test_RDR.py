import os
import tempfile
from tests.ATE.data.STDF.STDFRecordTest import STDFRecordTest
from ATE.data.STDF.RDR import RDR

#   Retest Data Record
#   Function:
#   Signals that the data in this STDF file is for retested parts. The data in 
#   this record,combined with information in theMIR, tells data filtering 
#   programs what data toreplace when processing retest data.

def test_RDR():
    
#   ATDF page 30
    expected_atdf = "RDR:"
#   record length in bytes    
    rec_len = 0;

#   STDF v4 page 34
    record = RDR()
    num_bins = 4
    record.set_value('NUM_BINS', num_bins)
    rec_len = 2;
    
    rtst_bin = [0, 1, 2, 65535]
    record.set_value('RTST_BIN', rtst_bin)
    rec_len += len(rtst_bin)*2;
    for elem in rtst_bin:
        expected_atdf += str(elem) + ","
    expected_atdf = expected_atdf[:-1]


#    Test serialization
#    1. Save RDR STDF record into a file
#    2. Read byte by byte and compare with expected value
    
    tf = tempfile.NamedTemporaryFile(delete=False)  
    
    f = open(tf.name, "wb")

    w_data = record.__repr__()
    f.write(w_data)
    f.close

    f = open(tf.name, "rb")
    
    stdfRecTest = STDFRecordTest(f, "<")
#   rec_len, rec_type, rec_sub
    stdfRecTest.assert_file_record_header(rec_len, 1, 70)
#   Test NUM_BINS, expected value num_bins
    stdfRecTest.assert_int(2, num_bins)
#   Test RTST_BIN, expected value rtst_bin
    stdfRecTest.assert_int_array(2, rtst_bin)

    f.close()    

#    Test de-serialization
#    1. Open STDF record from a file
#    2. Read record fields and compare with the expected value
#    
#    ToDo : make test with both endianness

    inst = RDR('V4', '<', w_data)
#   rec_len, rec_type, rec_sub
    stdfRecTest.assert_instance_record_header(inst , rec_len, 1, 70)
#   Test NUM_BINS, position 3, value of num_bins variable
    stdfRecTest.assert_instance_field(inst, 3, num_bins);
#   Test RTST_BIN, position 4, value of rtst_bin variable
    stdfRecTest.assert_instance_field(inst, 4, rtst_bin);
    
#   Test ATDF output
#   BUG, the atdf record is not according specification in page 30.
#   num_bins must be omitted in the ATDF output
    assert inst.to_atdf() == expected_atdf

#   ToDo: Test JSON output
    
    os.remove(tf.name)
