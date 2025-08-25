<?xml version="1.0" encoding="utf-8"?>
<xsl:stylesheet 
  version="3.0"
  xmlns:tei="http://www.tei-c.org/ns/1.0" 
  xmlns:hei="https://digi.ub.uni-heidelberg.de/schema/tei/heiEDITIONS"
  xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
  xmlns:xs="http://www.w3.org/2001/XMLSchema"
  >

<!-- 
    
-->  
     
  <xsl:output method="html"/>

  <!-- Identity template -->
  <xsl:mode on-no-match="shallow-copy" />

  
  
    <xsl:template match="tei:TEI | tei:text | tei:front">
        <div>
            <xsl:attribute name="class">
                <xsl:text>tei-</xsl:text>
                <xsl:value-of select="name()"/>
                <xsl:for-each select="@*">
                    <xsl:if test="name() = tokenize('ana rendition')">
                        <xsl:text> </xsl:text>
                        <xsl:value-of select="."/>
                    </xsl:if>
                </xsl:for-each>
            </xsl:attribute>
            <xsl:apply-templates select="node()"/>
        </div>    
    </xsl:template>

    <xsl:template match="tei:l | tei:p">
        <div>
            <span class="tei-container-n">    
                <xsl:attribute name="data-container-id" select="@xml:id"/>
                <xsl:value-of select="@n"/>
            </span>
            <xsl:apply-templates select="node()"/>
        </div>
    </xsl:template>

    <xsl:template match="tei:pb | tei:cb">
        <span>
            <xsl:attribute name="class">
                <xsl:text>tei-</xsl:text>
                <xsl:value-of select="name()"/>
                <xsl:for-each select="@*">
                    <xsl:if test="name() = ('ana', 'rendition', 'facs', 'n')">
                        <xsl:text> </xsl:text>
                        <xsl:value-of select="name()"/>
                        <xsl:text>-</xsl:text>
                        <xsl:value-of select="."/>
                    </xsl:if>
                </xsl:for-each>
            </xsl:attribute>
        </span>
        
    </xsl:template>

    
  
  
  
</xsl:stylesheet>
