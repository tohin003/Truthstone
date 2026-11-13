// After `protoc --ts_proto_out`, rename the output to the name the sources import.
import { renameSync } from "node:fs";

renameSync("src/generated/nordpaket/booking.ts", "src/generated/booking_pb.ts");
