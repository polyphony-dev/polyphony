module SinglePortRam #
(
  parameter DATA_WIDTH = 8,
  parameter ADDR_WIDTH = 4,
  parameter RAM_DEPTH = 1 << ADDR_WIDTH
)
(
  input CLK,
  input RST,
  input [ADDR_WIDTH-1:0] ADDR,
  input [DATA_WIDTH-1:0] D,
  input WE,
  output [DATA_WIDTH-1:0] Q
);

  reg [DATA_WIDTH-1:0] mem [0:RAM_DEPTH-1];
  reg [ADDR_WIDTH-1:0] read_addr;

  assign Q = mem[read_addr];
  always @ (posedge CLK) begin
    if (WE)
      mem[ADDR] <= D;
	read_addr <= ADDR;
  end
endmodule
